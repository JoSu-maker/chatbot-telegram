import os
import pytz
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# If modifying these scopes, delete the token.pickle file
SCOPES = ['https://www.googleapis.com/auth/calendar']

class GoogleCalendarService:
    def __init__(self):
        self.credentials = self._get_credentials()
        self.service = build('calendar', 'v3', credentials=self.credentials)
        self.calendar_id = os.getenv('GOOGLE_CALENDAR_ID')
        self.timezone = os.getenv('TIMEZONE', 'America/Caracas')

    def _get_credentials(self):
        creds = None
        # The file token.pickle stores the user's access and refresh tokens
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    os.getenv('GOOGLE_CALENDAR_CREDENTIALS'), SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        
        return creds

    def create_appointment(self, summary, start_datetime, end_datetime, description="", attendees=None):
        """Create a new calendar event"""
        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_datetime.isoformat(),
                'timeZone': self.timezone,
            },
            'end': {
                'dateTime': end_datetime.isoformat(),
                'timeZone': self.timezone,
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                    {'method': 'popup', 'minutes': 60},       # 1 hour before
                ],
            },
        }

        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]

        try:
            event = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event,
                sendUpdates='all'
            ).execute()
            return event.get('id')
        except Exception as e:
            print(f"Error creating calendar event: {e}")
            return None

    def get_available_slots(self, date, duration_minutes=30, working_hours=None):
        """Get available time slots for a given date"""
        if working_hours is None:
            working_hours = {
                'start': int(os.getenv('BUSINESS_HOURS_START', 8)),
                'end': int(os.getenv('BUSINESS_HOURS_END', 17))
            }

        # Set the timezone
        tz = pytz.timezone(self.timezone)
        
        # Create datetime objects for the start and end of the day
        start_dt = datetime.combine(date, datetime.min.time())
        start_dt = tz.localize(start_dt) + timedelta(hours=working_hours['start'])
        end_dt = datetime.combine(date, datetime.min.time())
        end_dt = tz.localize(end_dt) + timedelta(hours=working_hours['end'])
        
        # Get existing events for the day
        events_result = self.service.events().list(
            calendarId=self.calendar_id,
            timeMin=start_dt.isoformat(),
            timeMax=end_dt.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        # Generate time slots
        time_slots = []
        current_time = start_dt
        slot_duration = timedelta(minutes=duration_minutes)
        
        while current_time + slot_duration <= end_dt:
            slot_end = current_time + slot_duration
            
            # Check if the slot is available
            is_available = True
            for event in events:
                event_start = datetime.fromisoformat(event['start'].get('dateTime', event['start'].get('date')))
                event_end = datetime.fromisoformat(event['end'].get('dateTime', event['end'].get('date')))
                
                if (current_time < event_end and slot_end > event_start):
                    is_available = False
                    current_time = event_end  # Move to the end of this event
                    break
            
            if is_available:
                time_slots.append({
                    'start': current_time,
                    'end': slot_end
                })
                current_time += slot_duration
            else:
                # Move to the next possible slot start time
                current_time += timedelta(minutes=5)
        
        return time_slots

    def cancel_appointment(self, event_id):
        """Cancel a calendar event"""
        try:
            self.service.events().delete(
                calendarId=self.calendar_id,
                eventId=event_id,
                sendUpdates='all'
            ).execute()
            return True
        except Exception as e:
            print(f"Error canceling calendar event: {e}")
            return False

    def get_event(self, event_id):
        """Get event details"""
        try:
            return self.service.events().get(
                calendarId=self.calendar_id,
                eventId=event_id
            ).execute()
        except Exception as e:
            print(f"Error getting event: {e}")
            return None
