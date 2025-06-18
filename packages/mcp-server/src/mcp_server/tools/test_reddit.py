# src/ai_agent/tools/test_reddit.py
import os
import asyncio
import asyncpraw
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_reddit_connection():
    """Test the Reddit API connection and search functionality."""
    print("Testing Reddit API connection...")

    # Get credentials
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "RotterdamSafetyAnalyzer/1.0")

    print(f"Client ID: {client_id[:4]}... (length: {len(client_id) if client_id else 0})")
    print(f"Client Secret: {client_secret[:4]}... (length: {len(client_secret) if client_secret else 0})")
    print(f"User Agent: {user_agent}")

    try:
        # Initialize Reddit client
        reddit = asyncpraw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )

        print("\nTesting subreddit access...")
        for subreddit_name in ["Rotterdam", "Netherlands"]:
            try:
                print(f"\nSearching r/{subreddit_name}...")
                subreddit = await reddit.subreddit(subreddit_name)

                # Try to get some posts
                print("Recent posts:")
                async for post in subreddit.hot(limit=3):
                    print(f"- {post.title}")

                # Try a search
                print("\nSearching for 'Rotterdam Centrum'...")
                async for post in subreddit.search("Rotterdam Centrum", limit=3):
                    print(f"- {post.title}")

            except Exception as e:
                print(f"Error accessing r/{subreddit_name}: {str(e)}")

    except Exception as e:
        print(f"Error initializing Reddit client: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_reddit_connection())