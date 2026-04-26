import os
import io
from datetime import timedelta
from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv

load_dotenv()

class StorageService:
    def __init__(self):
        self.endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "admin")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "password")
        self.bucket_name = os.getenv("MINIO_BUCKET_NAME", "market-maps")
        
        # Use secure=False for local development without HTTPS
        self.secure = not self.endpoint.startswith("localhost")
        
        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure
        )

    def ensure_bucket_exists(self):
        """Ensure the target bucket exists, create it if it doesn't."""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                print(f"Created bucket '{self.bucket_name}'")
        except S3Error as e:
            print(f"Error checking/creating bucket: {e}")

    def upload_file(self, file_path: str, object_name: str, content_type: str = "application/octet-stream") -> str:
        """Upload a file from the local filesystem to MinIO."""
        try:
            self.client.fput_object(
                self.bucket_name,
                object_name,
                file_path,
                content_type=content_type
            )
            return object_name
        except S3Error as e:
            print(f"Failed to upload file {file_path}: {e}")
            return None

    def upload_text(self, text_content: str, object_name: str, content_type: str = "text/html") -> str:
        """Upload raw text content directly to MinIO."""
        try:
            # Convert string to bytes
            bytes_content = text_content.encode('utf-8')
            bytes_io = io.BytesIO(bytes_content)
            
            self.client.put_object(
                self.bucket_name,
                object_name,
                bytes_io,
                length=len(bytes_content),
                content_type=content_type
            )
            return object_name
        except S3Error as e:
            print(f"Failed to upload text content: {e}")
            return None

    def get_presigned_url(self, object_name: str, expires_in_hours: int = 1) -> str:
        """Generate a presigned URL valid for the specified number of hours."""
        if not object_name:
            return None
            
        try:
            url = self.client.presigned_get_object(
                self.bucket_name,
                object_name,
                expires=timedelta(hours=expires_in_hours)
            )
            return url
        except S3Error as e:
            print(f"Failed to generate presigned URL for {object_name}: {e}")
            return None

# Singleton instance
storage = StorageService()
