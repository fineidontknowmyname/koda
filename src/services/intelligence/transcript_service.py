from youtube_transcript_api import YouTubeTranscriptApi
import re

class YouTubeTranscriptService:
    def extract_video_id(self, url: str) -> str:
        """
        Extracts the video ID from a YouTube URL.
        Supports standard and short URLs.
        """
        # Regex for standard and short URLs
        regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
        match = re.search(regex, url)
        if match:
            return match.group(1)
        raise ValueError("Invalid YouTube URL")

    def fetch_transcript(self, video_url: str) -> str:
        """
        Fetches the transcript for a given YouTube video URL.
        Returns the combined text of the transcript.
        """
        try:
            video_id = self.extract_video_id(video_url)
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            
            # Combine all text parts
            full_text = " ".join([entry['text'] for entry in transcript_list])
            return full_text
            
        except Exception as e:
            print(f"Error fetching transcript: {e}")
            raise ValueError(f"Could not fetch transcript for {video_url}. Ensure the video has captions.")

transcript_service = YouTubeTranscriptService()
