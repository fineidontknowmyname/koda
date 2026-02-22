import asyncio
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.services.intelligence.youtube import youtube_service
from src.services.intelligence.summarizer import summarizer_service

async def main():
    print("--- Verifying YouTube Service ---")
    # Test video ID extraction
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ" # Never Gonna Give You Up
    video_id = youtube_service.extract_video_id(url)
    print(f"Extracted Video ID: {video_id}")
    
    if video_id == "dQw4w9WgXcQ":
        print("✅ Video ID extraction successful")
    else:
        print("❌ Video ID extraction failed")

    # Test Transcript (This might fail if no captions or network issues, but we test the import and call)
    print("\nAttempting to fetch transcript (may fail if no captions/network)...")
    transcript = youtube_service.get_transcript(video_id)
    if transcript:
        print(f"✅ Transcript fetched ({len(transcript)} chars)")
    else:
        print("⚠️ Transcript fetch failed or empty (expected if no captions/network)")

    print("\n--- Verifying Summarizer Service ---")
    # Test Summarizer
    dummy_text = "The quick brown fox jumps over the lazy dog. " * 20
    print("Sending text to summarizer...")
    try:
        summary = await summarizer_service.summarize_content(dummy_text)
        print(f"Summary: {summary}")
        if summary and "Failed" not in summary:
            print("✅ Summarizer service working")
        else:
             print("❌ Summarizer returned failure message")
    except Exception as e:
        print(f"❌ Summarizer threw exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
