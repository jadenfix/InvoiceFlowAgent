"""
S3 service for file operations
"""
import json
import time
from typing import Optional, Dict, Any
import boto3
import aiobotocore.session
from botocore.exceptions import ClientError, NoCredentialsError
from aiobotocore.exceptions import ClientError as AioClientError

from ..core.config import settings, get_s3_config
from ..core.logging import get_logger, log_processing_step, log_error


logger = get_logger(__name__)


class S3Service:
    """S3 service for file operations"""
    
    def __init__(self):
        self.s3_config = get_s3_config()
        self.bucket = settings.S3_BUCKET
    
    async def download_file(self, s3_key: str, request_id: str) -> Optional[bytes]:
        """
        Download a file from S3
        
        Args:
            s3_key: S3 object key
            request_id: Request ID for logging
            
        Returns:
            File content as bytes or None if failed
        """
        log_processing_step("s3_download", request_id, s3_key=s3_key)
        
        try:
            session = aiobotocore.session.get_session()
            
            async with session.create_client('s3', **self.s3_config) as s3_client:
                response = await s3_client.get_object(Bucket=self.bucket, Key=s3_key)
                content = await response['Body'].read()
                
                logger.info(f"Downloaded {len(content)} bytes from s3://{self.bucket}/{s3_key} for request {request_id}")
                return content
                
        except AioClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code == 'NoSuchKey':
                logger.error(f"File not found: s3://{self.bucket}/{s3_key} for request {request_id}")
            elif error_code == 'AccessDenied':
                logger.error(f"Access denied to s3://{self.bucket}/{s3_key} for request {request_id}")
            else:
                log_error(e, {"operation": "s3_download", "request_id": request_id, "s3_key": s3_key})
            
            return None
            
        except NoCredentialsError as e:
            log_error(e, {"operation": "s3_download", "request_id": request_id})
            logger.error(f"AWS credentials not found for request {request_id}")
            return None
            
        except Exception as e:
            log_error(e, {"operation": "s3_download", "request_id": request_id, "s3_key": s3_key})
            return None
    
    async def upload_file(self, content: bytes, s3_key: str, request_id: str, content_type: str = 'application/json') -> bool:
        """
        Upload a file to S3
        
        Args:
            content: File content as bytes
            s3_key: S3 object key
            request_id: Request ID for logging
            content_type: MIME type of the content
            
        Returns:
            True if successful, False otherwise
        """
        log_processing_step("s3_upload", request_id, s3_key=s3_key, size=len(content))
        
        try:
            session = aiobotocore.session.get_session()
            
            async with session.create_client('s3', **self.s3_config) as s3_client:
                await s3_client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=content,
                    ContentType=content_type,
                    Metadata={
                        'request_id': request_id,
                        'upload_time': str(int(time.time())),
                        'service': 'extract-service'
                    }
                )
                
                logger.info(f"Uploaded {len(content)} bytes to s3://{self.bucket}/{s3_key} for request {request_id}")
                return True
                
        except AioClientError as e:
            log_error(e, {"operation": "s3_upload", "request_id": request_id, "s3_key": s3_key})
            return False
            
        except NoCredentialsError as e:
            log_error(e, {"operation": "s3_upload", "request_id": request_id})
            logger.error(f"AWS credentials not found for request {request_id}")
            return False
            
        except Exception as e:
            log_error(e, {"operation": "s3_upload", "request_id": request_id, "s3_key": s3_key})
            return False
    
    async def upload_json(self, data: Dict[str, Any], s3_key: str, request_id: str) -> bool:
        """
        Upload JSON data to S3
        
        Args:
            data: Dictionary to serialize as JSON
            s3_key: S3 object key
            request_id: Request ID for logging
            
        Returns:
            True if successful, False otherwise
        """
        try:
            json_content = json.dumps(data, indent=2, default=str).encode('utf-8')
            return await self.upload_file(json_content, s3_key, request_id, 'application/json')
            
        except Exception as e:
            log_error(e, {"operation": "s3_upload_json", "request_id": request_id, "s3_key": s3_key})
            return False
    
    def generate_raw_ocr_key(self, request_id: str) -> str:
        """Generate S3 key for raw OCR data"""
        return f"extracted/raw/{request_id}.json"
    
    def generate_processed_key(self, request_id: str) -> str:
        """Generate S3 key for processed extraction data"""
        return f"extracted/processed/{request_id}.json"
    
    async def health_check(self) -> bool:
        """Health check for S3 service"""
        try:
            session = aiobotocore.session.get_session()
            
            async with session.create_client('s3', **self.s3_config) as s3_client:
                # Try to list objects (limited to 1) to test connectivity
                await s3_client.list_objects_v2(Bucket=self.bucket, MaxKeys=1)
                return True
                
        except AioClientError as e:
            error_code = e.response['Error']['Code']
            
            if error_code == 'NoSuchBucket':
                logger.error(f"S3 bucket does not exist: {self.bucket}")
            elif error_code == 'AccessDenied':
                logger.error(f"Access denied to S3 bucket: {self.bucket}")
            else:
                log_error(e, {"operation": "s3_health_check"})
            
            return False
            
        except NoCredentialsError as e:
            log_error(e, {"operation": "s3_health_check"})
            logger.error("AWS credentials not found for S3 health check")
            return False
            
        except Exception as e:
            log_error(e, {"operation": "s3_health_check"})
            return False


# Create service instance
s3_service = S3Service() 