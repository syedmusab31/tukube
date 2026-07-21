from google_auth_oauthlib.flow import InstalledAppFlow

# Request permission to upload videos to YouTube
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
credentials = flow.run_local_server(port=0)

print("\n--- COPY THESE CRITICAL VALUES FOR GITHUB SECRETS ---")
print("CLIENT_ID:", credentials.client_id)
print("CLIENT_SECRET:", credentials.client_secret)
print("REFRESH_TOKEN:", credentials.refresh_token)