"""Package metadata for Whisper Dictation."""

from setuptools import find_packages, setup


setup(
    name="whisper-dictation-mac",
    version="0.4.0",
    description="Local push-to-talk dictation for macOS",
    python_requires=">=3.10,<3.14",
    package_dir={"": "src"},
    packages=find_packages("src"),
    install_requires=[
        "mlx-whisper>=0.4.1",
        "openai-whisper>=20231117",
        "sounddevice>=0.4.6",
        "numpy>=1.24.0",
        "PyQt6>=6.5.0",
        "pynput>=1.7.7",
        "pyperclip>=1.8.2",
        "scipy>=1.11.0",
        "imageio-ffmpeg>=0.6.0",
    ],
)
