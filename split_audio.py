import os
import subprocess
from pathlib import Path

INPUT_FILE = "input.mp3"      # άλλαξέ το
OUTPUT_DIR = "chunks"
CHUNK_SECONDS = 15 * 60       # 15 λεπτά
OVERLAP_SECONDS = 10          # 10 sec overlap

Path(OUTPUT_DIR).mkdir(exist_ok=True)

def get_duration(file_path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())

duration = get_duration(INPUT_FILE)

start = 0
index = 1

while start < duration:
    output_file = os.path.join(OUTPUT_DIR, f"chunk_{index:03d}.mp3")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss", str(start),
            "-i", INPUT_FILE,
            "-t", str(CHUNK_SECONDS + OVERLAP_SECONDS),
            "-c", "copy",
            output_file,
        ],
        check=True,
    )

    print(f"Created: {output_file} | start={start}s")

    start += CHUNK_SECONDS
    index += 1

print("Done.")