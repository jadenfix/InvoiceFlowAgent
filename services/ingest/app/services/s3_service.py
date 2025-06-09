"""
S3 service for file uploads
"""
import asyncio
import time
from typing import Optional, Tuple, Dict, Any
from datetime import datetime
import uuid
import aiofiles
import aiobotocore
from botocore.exceptions import ClientError, NoCredentialsError
from tenacity import retry, stop_after_attempt, wait_exponential

from ..core.config import settings, get_s3_config
from ..core.logging import get_logger, log_function_call, log_function_result, log_error


logger = get_logger(__name__)


class S3Service:
    """S3 service for file uploads"""
    
    def __init__(self):
        self.bucket_name = settings.S3_BUCKET
        self.s3_config = get_s3_config()
        self.session = None
    
    async def _get_session(self):
        """Get or create aiobotocore session"""
        if self.session is None:
            self.session = aiobotocore.get_session()
        return self.session
    
    @retry(
        stop=stop_after_attempt(settings.MAX_RETRIES),
        wait=wait_exponential(
            multiplier=settings.RETRY_DELAY_SECONDS,
            max=60
        )
    )
    async def upload_file(self, 
                         file_content: bytes, 
                         filename: str, 
                         request_id: str) -> Tuple[str, bool]:
        """
        Upload file to S3
        
        Args:
            file_content: File content as bytes
            filename: Original filename
            request_id: Unique request identifier
            
        Returns:
            Tuple of (s3_key, success)
        """
        log_function_call("S3Service.upload_file", 
                         filename=filename, request_id=request_id)
        start_time = time.time()
        
        # Generate S3 key
        s3_key = f"raw/{request_id}.pdf"
        
        try:
            session = await self._get_session()
            
            async with session.create_client('s3', **self.s3_config) as s3_client:
                # Upload file
                await s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=file_content,
                    ContentType='application/pdf',
                    Metadata={
                        'original_filename': filename,
                        'request_id': request_id,
                        'upload_timestamp': datetime.utcnow().isoformat()
                    }
                )
                
                logger.info(f"Successfully uploaded file to S3: {s3_key}")
                return s3_key, True
                
        except NoCredentialsError as e:
            log_error(e, {"operation": "s3_upload", "request_id": request_id})
            logger.error("AWS credentials not found")
            return s3_key, False
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            log_error(e, {
                "operation": "s3_upload", 
                "request_id": request_id,
                "error_code": error_code
            })
            
            if error_code in ['NoSuchBucket', 'AccessDenied']:
                logger.error(f"S3 bucket error: {error_code}")
                return s3_key, False
            
            # Re-raise for retry
            raise
            
        except Exception as e:
            log_error(e, {"operation": "s3_upload", "request_id": request_id})
            raise
            
        finally:
            log_function_result("S3Service.upload_file", 
                              s3_key if 's3_key' in locals() else None,
                              time.time() - start_time)
    
    async def delete_file(self, s3_key: str) -> bool:
        """Delete file from S3"""
        try:
            session = await self._get_session()
            
            async with session.create_client('s3', **self.s3_config) as s3_client:
                await s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=s3_key
                )
                logger.info(f"Successfully deleted file from S3: {s3_key}")
                return True
                
        except Exception as e:
            log_error(e, {"operation": "s3_delete", "s3_key": s3_key})
            return False
    
    async def file_exists(self, s3_key: str) -> bool:
        """Check if file exists in S3"""
        try:
            session = await self._get_session()
            
            async with session.create_client('s3', **self.s3_config) as s3_client:
                await s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key=s3_key
                )
                return True
                
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise
            
        except Exception as e:
            log_error(e, {"operation": "s3_head", "s3_key": s3_key})
            return False
    
    async def health_check(self) -> bool:
        """Health check for S3 connectivity"""
        try:
            session = await self._get_session()
            
            async with session.create_client('s3', **self.s3_config) as s3_client:
                # Try to list objects with limit 1
                await s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    MaxKeys=1
                )
                return True
                
        except Exception as e:
            log_error(e, {"operation": "s3_health_check"})
            return False
    
    async def get_file_metadata(self, s3_key: str) -> Optional[Dict[str, Any]]:
        """Get file metadata from S3"""
        try:
            session = await self._get_session()
            
            async with session.create_client('s3', **self.s3_config) as s3_client:
                response = await s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key=s3_key
                )
                
                return {
                    'size': response.get('ContentLength'),
                    'last_modified': response.get('LastModified'),
                    'content_type': response.get('ContentType'),
                    'metadata': response.get('Metadata', {})
                }
                
        except Exception as e:
            log_error(e, {"operation": "s3_get_metadata", "s3_key": s3_key})
            return None


# Create service instance
s3_service = S3Service() 