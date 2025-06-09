"""
Storage service for uploading files to S3 with retry logic
"""
import asyncio
import io
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import aiofiles

from ..core.config import settings, get_s3_config
from ..core.logging import get_logger, log_function_call, log_function_result, log_error, log_performance_metrics
from ..models.invoice import InvoiceStatus


logger = get_logger(__name__)


class S3StorageService:
    """S3 storage service with retry logic and error handling"""
    
    def __init__(self):
        self.s3_client = None
        self.bucket_name = settings.S3_BUCKET
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize S3 client with configuration"""
        try:
            s3_config = get_s3_config()
            self.s3_client = boto3.client('s3', **s3_config)
            logger.info(f"S3 client initialized for bucket {self.bucket_name}")
        except Exception as e:
            log_error(e, {"operation": "s3_client_init"})
            raise
    
    def _generate_s3_key(self, source: str, filename: str) -> str:
        """Generate S3 key for a file"""
        timestamp = datetime.now(timezone.utc)
        clean_filename = Path(filename).name
        date_prefix = timestamp.strftime("%Y/%m/%d")
        
        if '.' in clean_filename:
            name, ext = clean_filename.rsplit('.', 1)
            return f"raw/{source}/{date_prefix}/{name}_{int(timestamp.timestamp())}.{ext}"
        else:
            return f"raw/{source}/{date_prefix}/{clean_filename}_{int(timestamp.timestamp())}"
    
    def _generate_error_s3_key(self, source: str, filename: str, error_type: str) -> str:
        """Generate S3 key for error files"""
        clean_filename = Path(filename).name
        timestamp = datetime.now(timezone.utc)
        date_prefix = timestamp.strftime("%Y/%m/%d")
        
        if len(clean_filename.split('.')) > 1:
            name, ext = clean_filename.rsplit('.', 1)
            return f"error/{error_type}/{source}/{date_prefix}/{name}_{int(timestamp.timestamp())}.{ext}"
        else:
            return f"error/{error_type}/{source}/{date_prefix}/{clean_filename}_{int(timestamp.timestamp())}"
    
    async def health_check(self) -> bool:
        """Check if S3 is accessible"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: self.s3_client.list_objects_v2(Bucket=self.bucket_name, MaxKeys=1)
            )
            return True
        except Exception:
            return False
    
    @retry(
        stop=stop_after_attempt(settings.MAX_RETRIES),
        wait=wait_exponential(multiplier=settings.RETRY_DELAY, max=60),
        retry=retry_if_exception_type((ClientError, BotoCoreError))
    )
    async def upload_file(self, 
                         content: bytes, 
                         filename: str, 
                         source: str,
                         content_type: str = "application/octet-stream",
                         metadata: Optional[Dict[str, str]] = None) -> tuple[str, bool]:
        """Upload file to S3 with retry logic"""
        log_function_call("S3StorageService.upload_file", 
                         filename=filename, source=source, size=len(content))
        start_time = time.time()
        
        s3_key = self._generate_s3_key(source, filename)
        
        try:
            s3_metadata = {
                "source": source,
                "original-filename": filename,
                "uploaded-at": datetime.now(timezone.utc).isoformat(),
                "file-size": str(len(content)),
            }
            
            if metadata:
                for key, value in metadata.items():
                    s3_metadata[f"custom-{key}"] = str(value)
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=content,
                    ContentType=content_type,
                    Metadata=s3_metadata,
                    ServerSideEncryption='AES256'
                )
            )
            
            logger.info(f"Successfully uploaded {filename} to {s3_key}")
            
            duration = time.time() - start_time
            log_performance_metrics(
                "s3_upload",
                duration,
                file_size=len(content)
            )
            
            return s3_key, True
            
        except Exception as e:
            log_error(e, {
                "filename": filename,
                "source": source,
                "s3_key": s3_key,
                "file_size": len(content)
            })
            return s3_key, False
        finally:
            log_function_result("S3StorageService.upload_file", s3_key, time.time() - start_time)
    
    async def _verify_upload(self, s3_key: str, expected_size: int) -> None:
        """Verify that upload was successful"""
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            )
            
            actual_size = response.get('ContentLength', 0)
            if actual_size != expected_size:
                raise ValueError(f"Upload verification failed: expected {expected_size} bytes, got {actual_size}")
                
        except Exception as e:
            log_error(e, {"s3_key": s3_key, "expected_size": expected_size})
            raise
    
    async def move_to_error_folder(self, s3_key: str, error_type: str) -> str:
        """Move file to error folder"""
        try:
            path_parts = s3_key.split('/')
            source = path_parts[1] if len(path_parts) >= 2 else "unknown"
            filename = path_parts[-1]
            
            timestamp = datetime.now(timezone.utc)
            date_prefix = timestamp.strftime("%Y/%m/%d")
            error_key = f"error/{error_type}/{source}/{date_prefix}/{filename}"
            
            copy_source = {'Bucket': self.bucket_name, 'Key': s3_key}
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.copy_object(
                    CopySource=copy_source,
                    Bucket=self.bucket_name,
                    Key=error_key
                )
            )
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            )
            
            logger.info(f"Moved {s3_key} to error folder: {error_key}")
            return error_key
            
        except Exception as e:
            log_error(e, {"s3_key": s3_key, "error_type": error_type})
            raise
    
    async def download_file(self, s3_key: str) -> bytes:
        """Download file from S3"""
        log_function_call("S3StorageService.download_file", s3_key=s3_key)
        start_time = time.time()
        
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.get_object(Bucket=self.bucket_name, Key=s3_key)
            )
            
            content = response['Body'].read()
            
            # Log performance metrics
            duration = time.time() - start_time
            log_performance_metrics(
                "s3_download",
                duration,
                file_size=len(content),
                download_speed_mbps=round((len(content) / (1024 * 1024)) / duration, 2) if duration > 0 else 0
            )
            
            return content
            
        except Exception as e:
            log_error(e, {"s3_key": s3_key})
            raise
        finally:
            log_function_result("S3StorageService.download_file", len(content) if 'content' in locals() else 0, time.time() - start_time)
    
    async def file_exists(self, s3_key: str) -> bool:
        """Check if file exists in S3"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise
    
    async def get_file_metadata(self, s3_key: str) -> Dict[str, Any]:
        """Get file metadata from S3"""
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            )
            
            return {
                'size': response.get('ContentLength', 0),
                'last_modified': response.get('LastModified'),
                'content_type': response.get('ContentType', ''),
                'metadata': response.get('Metadata', {}),
                'etag': response.get('ETag', '').strip('"'),
            }
            
        except Exception as e:
            log_error(e, {"s3_key": s3_key})
            raise
    
    async def list_files(self, prefix: str = "", max_keys: int = 1000) -> List[Dict[str, Any]]:
        """List files in S3 bucket with optional prefix"""
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=prefix,
                    MaxKeys=max_keys
                )
            )
            
            files = []
            for obj in response.get('Contents', []):
                files.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'],
                    'etag': obj['ETag'].strip('"'),
                })
            
            return files
            
        except Exception as e:
            log_error(e, {"prefix": prefix})
            raise
    
    async def delete_file(self, s3_key: str) -> bool:
        """Delete file from S3"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            )
            
            logger.info(f"Deleted file from S3: {s3_key}")
            return True
            
        except Exception as e:
            log_error(e, {"s3_key": s3_key})
            return False
    
    async def generate_presigned_url(self, s3_key: str, expiration: int = 3600) -> str:
        """Generate presigned URL for S3 object"""
        try:
            url = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': self.bucket_name, 'Key': s3_key},
                    ExpiresIn=expiration
                )
            )
            
            return url
            
        except Exception as e:
            log_error(e, {"s3_key": s3_key})
            raise


# Global storage service instance
storage_service = S3StorageService() 