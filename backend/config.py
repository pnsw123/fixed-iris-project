from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from .env"""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    reload: bool = True

    # Models
    iris_sam_model: str = "./models/IrisSAM_model.pt"
    # Base SAM checkpoint (used if compatible with the fine-tuned weights)
    sam_checkpoint: str = "./models/sam_vit_b_01ec64.pth"
    # SAM backbone to use: "auto" (detect from fine-tuned weights), or one of ["vit_b", "vit_l", "vit_h"]
    sam_model_type: str = "auto"
    esrgan_model: str = "../public/models/realesr-general-x4v3.pth"

    # Device
    device: str = "mps"  # mps, cuda, or cpu

    # CORS
    cors_origins: List[str] = [
        "http://localhost:3005",
        "http://localhost:3000",
        "https://localhost:3005",
        "https://10.0.0.104:3005",
        "https://10.0.0.104:3000",
        "http://10.0.0.104:3005",
        "http://10.0.0.104:3000"
    ]

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
