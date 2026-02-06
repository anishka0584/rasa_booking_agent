from typing import Any, Text, Dict, List
from rasa_sdk import Tracker, FormValidationAction, Action
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet
from datetime import datetime, timedelta
import re


class ValidateHotelBookingForm(FormValidationAction):
    """Validates hotel booking form slots"""

    def name(self) -> Text:
        return "validate_hotel_booking_form"

    def parse_date(self, date_string: Text) -> Text:
        """Convert relative dates like 'tomorrow', 'today' to actual dates"""
        if not date_string:
            return ""
            
        date_string = date_string.lower().strip()
        today = datetime.now()
        
        # Handle relative dates
        if date_string in ["today"]:
            return today.strftime("%d %b")
        elif date_string in ["tomorrow", "tmrw", "tommorow"]:
            return (today + timedelta(days=1)).strftime("%d %b")
        elif date_string in ["day after tomorrow", "day after tmrw"]:
            return (today + timedelta(days=2)).strftime("%d %b")
        elif "next week" in date_string:
            return (today + timedelta(days=7)).strftime("%d %b")
        
        # Handle "5th", "10th" etc for current/next month
        day_match = re.match(r'^(\d{1,2})(st|nd|rd|th)?$', date_string)
        if day_match:
            day = int(day_match.group(1))
            if 1 <= day <= 31:
                try:
                    # Assume current month if day is in future, else next month
                    if day >= today.day:
                        target_date = today.replace(day=day)
                    else:
                        # Next month
                        if today.month == 12:
                            target_date = today.replace(month=1, day=day, year=today.year + 1)
                        else:
                            target_date = today.replace(month=today.month + 1, day=day)
                    return target_date.strftime("%d %b")
                except ValueError:
                    pass
        
        # Try to parse and normalize existing dates like "8 feb" -> "08 Feb"
        try:
            for fmt in ["%d %b", "%d %B", "%b %d", "%B %d"]:
                try:
                    parsed = datetime.strptime(date_string, fmt)
                    parsed = parsed.replace(year=today.year)
                    if parsed < today:
                        parsed = parsed.replace(year=today.year + 1)
                    return parsed.strftime("%d %b")  # Normalized format
                except ValueError:
                    continue
        except:
            pass
        
        # Return as-is if parsing fails
        return date_string

    def extract_date_range(self, text: Text) -> Dict[Text, Any]:
        """Extract check-in and check-out dates from text like '10th to 12th'"""
        # Pattern: "10th to 12th", "1 jan to 5 jan", "5 to 8 may"
        patterns = [
            (r'(\d{1,2})\s+to\s+(\d{1,2})\s+(\w+)', 'day_to_day_month'),  # 5 to 8 may
            (r'(\d{1,2}\s+\w+)\s+to\s+(\d{1,2}\s+\w+)', 'date_to_date'),  # 1 jan to 5 jan
            (r'(\d{1,2}(?:st|nd|rd|th)?)\s+to\s+(\d{1,2}(?:st|nd|rd|th)?)', 'ordinal_to_ordinal'),  # 10th to 12th
        ]
        
        for pattern, pattern_type in patterns:
            match = re.search(pattern, text.lower())
            if match:
                if pattern_type == 'day_to_day_month':  # "5 to 8 may"
                    check_in = f"{match.group(1)} {match.group(3)}"
                    check_out = f"{match.group(2)} {match.group(3)}"
                elif pattern_type == 'date_to_date':  # "1 jan to 5 jan"
                    check_in = match.group(1)
                    check_out = match.group(2)
                else:  # "10th to 12th"
                    check_in = match.group(1)
                    check_out = match.group(2)
                
                return {
                    "check_in_date": self.parse_date(check_in),
                    "check_out_date": self.parse_date(check_out)
                }
        
        return {}

        

    def extract_duration(self, text: Text) -> int:
        """Extract duration like 'for 5 days', 'for 3 nights'"""
        if not text:
            return None
            
        patterns = [
            r'for\s+(\d+)\s+days?',
            r'for\s+(\d+)\s+nights?',
            r'(\d+)\s+days?\s+stay',
            r'(\d+)\s+nights?\s+stay',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                return int(match.group(1))
        
        return None

    def is_valid_date(self, date_string: Text) -> bool:
        """Check if string looks like a date"""
        if not date_string or len(date_string.strip()) == 0:
            return False
        
        # Check if it contains obvious non-date words
        non_date_words = ['banana', 'hello', 'hi', 'thanks', 'please', 'yes', 'no', 'ok', 'okay', 'sure']
        if date_string.lower() in non_date_words:
            return False
        
        # Simple check: should have at least one letter or number pattern
        date_patterns = [
            r'\d+\s+\w+',  # "5 may"
            r'\w+\s+\d+',  # "may 5"
            r'\d+\s+\w+\s+\d+',  # "5 may 2025"
        ]
        
        for pattern in date_patterns:
            if re.search(pattern, date_string.lower()):
                return True
        
        return False

    def calculate_checkout(self, checkin_date: Text, duration_days: int) -> Text:
        """Calculate checkout date from check-in date and duration"""
        try:
            today = datetime.now()
            
            # Try to parse different date formats
            for fmt in ["%d %b", "%d %B", "%b %d", "%B %d"]:
                try:
                    parsed = datetime.strptime(checkin_date, fmt)
                    # Add current year
                    parsed = parsed.replace(year=today.year)
                    # If date is in the past, use next year
                    if parsed < today:
                        parsed = parsed.replace(year=today.year + 1)
                    
                    checkout = parsed + timedelta(days=duration_days)
                    return checkout.strftime("%d %b")
                except ValueError:
                    continue
            
            # If parsing fails, return a default
            return checkin_date
        except Exception as e:
            return checkin_date

    def validate_city(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validate city - should be text, not empty"""
        if not value or len(value.strip()) == 0:
            dispatcher.utter_message(text="Please enter a city name.")
            return {"city": None}
        
        # Clean the value
        value = value.strip()
        
        # Check if it's only digits
        if value.isdigit():
            dispatcher.utter_message(text="That doesn't look like a city name. Please enter a valid city.")
            return {"city": None}
        
        # Check against common non-city words
        non_city_words = ['banana', 'hello', 'hi', 'thanks', 'please', 'yes', 'no', 'ok', 'okay', 'tomorrow', 'today', 'sure']
        if value.lower() in non_city_words:
            dispatcher.utter_message(text="That doesn't look like a city name. Please enter a valid city.")
            return {"city": None}
        
        # Capitalize first letter of each word
        return {"city": value.title()}

    def validate_check_in_date(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validate check-in date and extract date range if provided"""
        
        # Check if user provided a date range (e.g., "10th to 12th")
        latest_message = tracker.latest_message.get('text', '')
        date_range = self.extract_date_range(latest_message)
        
        if date_range:
            # User provided both dates!
            dispatcher.utter_message(
                text=f"Got it! Check-in on {date_range['check_in_date']} and check-out on {date_range['check_out_date']}."
            )
            return date_range
        
        # Parse single date
        parsed_date = self.parse_date(value)
        
        # Basic validation - check if it looks like a date
        if self.is_valid_date(parsed_date):
            # Check if duration was mentioned in initial booking request
            initial_text = tracker.slots.get('initial_message', '')
            duration = self.extract_duration(initial_text)
            
            if duration:
                # Calculate checkout date
                checkout_date = self.calculate_checkout(parsed_date, duration)
                dispatcher.utter_message(
                    text=f"Check-in: {parsed_date}, Check-out: {checkout_date} ({duration} days)"
                )
                return {
                    "check_in_date": parsed_date,
                    "check_out_date": checkout_date
                }
            
            return {"check_in_date": parsed_date}
        else:
            dispatcher.utter_message(
                text="That doesn't look like a date. Please enter a valid date (e.g., '5 may', 'tomorrow', '10th')."
            )
            return {"check_in_date": None}

    def validate_check_out_date(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validate check-out date"""
        parsed_date = self.parse_date(value)
        
        if self.is_valid_date(parsed_date):
            return {"check_out_date": parsed_date}
        else:
            dispatcher.utter_message(
                text="That doesn't look like a date. Please enter a valid date (e.g., '8 may', 'tomorrow', '15th')."
            )
            return {"check_out_date": None}

    def validate_number_of_guests(
        self,
        value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validate number of guests - should be a positive number"""
        
        # Check if value is None or empty
        if value is None or (isinstance(value, str) and len(value.strip()) == 0):
            dispatcher.utter_message(
                text="Please enter the number of guests."
            )
            return {"number_of_guests": None}
        
        try:
            # Handle text numbers like "two", "three"
            word_to_num = {
                "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
            }
            
            if isinstance(value, str):
                value_lower = value.lower().strip()
                if value_lower in word_to_num:
                    guests = word_to_num[value_lower]
                else:
                    # Try to extract just the number if mixed text
                    num_match = re.search(r'\d+', value)
                    if num_match:
                        guests = int(num_match.group())
                    else:
                        raise ValueError("Not a number")
            else:
                guests = int(float(value))
            
            if 1 <= guests <= 50:
                return {"number_of_guests": guests}
            else:
                dispatcher.utter_message(
                    text="Number of guests should be between 1 and 50. Please enter again."
                )
                return {"number_of_guests": None}
        except (ValueError, TypeError):
            dispatcher.utter_message(
                text="That doesn't look like a number. Please enter the number of guests (e.g., '2', 'three')."
            )
            return {"number_of_guests": None}


class ActionStoreInitialMessage(Action):
    """Store the initial booking message and extract/parse dates"""
    
    def name(self) -> Text:
        return "action_store_initial_message"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        latest_message = tracker.latest_message.get('text', '')
        entities = tracker.latest_message.get('entities', [])
        
        slots_to_set = [SlotSet("initial_message", latest_message)]
        
        # Parse date entities if they exist
        validator = ValidateHotelBookingForm()
        
        for entity in entities:
            if entity['entity'] == 'check_in_date':
                parsed_date = validator.parse_date(entity['value'])
                slots_to_set.append(SlotSet("check_in_date", parsed_date))
            elif entity['entity'] == 'check_out_date':
                parsed_date = validator.parse_date(entity['value'])
                slots_to_set.append(SlotSet("check_out_date", parsed_date))
        
        return slots_to_set