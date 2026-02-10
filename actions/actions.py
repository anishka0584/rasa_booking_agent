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
                    return parsed.strftime("%d %b")
                except ValueError:
                    continue
        except:
            pass
        
        # Return as-is if parsing fails
        return date_string

    def extract_date_range(self, text: Text) -> Dict[Text, Any]:
        """Extract check-in and check-out dates from text like '10th to 12th' or 'from 3 may to 5 may'"""
        patterns = [
            # "from 3 may to 5 may"
            (r'from\s+(\d{1,2}\s+\w+)\s+to\s+(\d{1,2}\s+\w+)', 'date_to_date'),
            # "from tomorrow to 5 may"
            (r'from\s+(tomorrow|today|next week)\s+to\s+(\d{1,2}\s+\w+)', 'relative_to_date'),
            # "from 10th to 15th"
            (r'from\s+(\d{1,2}(?:st|nd|rd|th)?)\s+to\s+(\d{1,2}(?:st|nd|rd|th)?)', 'ordinal_to_ordinal'),
            # "5 to 8 may"
            (r'(\d{1,2})\s+to\s+(\d{1,2})\s+(\w+)', 'day_to_day_month'),
            # "1 jan to 5 jan"
            (r'(\d{1,2}\s+\w+)\s+to\s+(\d{1,2}\s+\w+)', 'date_to_date'),
            # "10th to 12th"
            (r'(\d{1,2}(?:st|nd|rd|th)?)\s+to\s+(\d{1,2}(?:st|nd|rd|th)?)', 'ordinal_to_ordinal'),
        ]
        
        for pattern, pattern_type in patterns:
            match = re.search(pattern, text.lower())
            if match:
                if pattern_type == 'day_to_day_month':
                    check_in = f"{match.group(1)} {match.group(3)}"
                    check_out = f"{match.group(2)} {match.group(3)}"
                elif pattern_type == 'relative_to_date':
                    check_in = match.group(1)
                    check_out = match.group(2)
                else:
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
        
        # Pure numbers (like 5555, 6666) are NOT valid dates
        if str(date_string).strip().isdigit():
            # Check if it's a reasonable day number (1-31)
            try:
                num = int(date_string)
                if not (1 <= num <= 31):
                    return False
            except:
                return False
        
        non_date_words = ['banana', 'hello', 'hi', 'thanks', 'please', 'yes', 'no', 'ok', 'okay', 'sure']
        if date_string.lower() in non_date_words:
            return False
        
        date_patterns = [
            r'\d+\s+\w+',
            r'\w+\s+\d+',
            r'\d+\s+\w+\s+\d+',
        ]
        
        for pattern in date_patterns:
            if re.search(pattern, date_string.lower()):
                return True
        
        return False

    def calculate_checkout(self, checkin_date: Text, duration_days: int) -> Text:
        """Calculate checkout date from check-in date and duration"""
        try:
            today = datetime.now()
            
            for fmt in ["%d %b", "%d %B", "%b %d", "%B %d"]:
                try:
                    parsed = datetime.strptime(checkin_date, fmt)
                    parsed = parsed.replace(year=today.year)
                    if parsed < today:
                        parsed = parsed.replace(year=today.year + 1)
                    
                    checkout = parsed + timedelta(days=duration_days)
                    return checkout.strftime("%d %b")
                except ValueError:
                    continue
            
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
        """Validate city - only when requested"""
        
        # CRITICAL: Only validate when form is asking for city
        if tracker.get_slot("requested_slot") != "city":
            return {"city": tracker.slots.get("city")}

        if not value or len(value.strip()) == 0:
            dispatcher.utter_message(text="Please enter a city name.")
            return {"city": None}
        
        value = value.strip()
        
        if value.isdigit():
            dispatcher.utter_message(text="That doesn't look like a city name. Please enter a valid city.")
            return {"city": None}
        
        non_city_words = ['banana', 'hello', 'hi', 'thanks', 'please', 'yes', 'no', 'ok', 'okay', 'tomorrow', 'today', 'sure']
        if value.lower() in non_city_words:
            dispatcher.utter_message(text="That doesn't look like a city name. Please enter a valid city.")
            return {"city": None}
        
        return {"city": value.title()}

    def validate_check_in_date(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validate check-in date - only when requested"""
        
        # CRITICAL: Only validate when form is asking for check-in date
        if tracker.get_slot("requested_slot") != "check_in_date":
            return {"check_in_date": tracker.slots.get("check_in_date")}

        latest_message = tracker.latest_message.get('text', '')
        date_range = self.extract_date_range(latest_message)
        
        if date_range:
            dispatcher.utter_message(
                text=f"Got it! Check-in on {date_range['check_in_date']} and check-out on {date_range['check_out_date']}."
            )
            return date_range
        
        parsed_date = self.parse_date(value)
        
        if self.is_valid_date(parsed_date):
            initial_text = tracker.slots.get('initial_message', '')
            duration = self.extract_duration(initial_text)
            
            if duration:
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
                text="That doesn't look like a date. Please enter a valid date (e.g., '5 may', 'tomorrow')."
            )
            return {"check_in_date": None}

    def validate_check_out_date(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validate check-out date - only when requested"""
        
        # CRITICAL: Only validate when form is asking for check-out date
        if tracker.get_slot("requested_slot") != "check_out_date":
            return {"check_out_date": tracker.slots.get("check_out_date")}

        parsed_date = self.parse_date(value)
        
        if self.is_valid_date(parsed_date):
            return {"check_out_date": parsed_date}
        else:
            dispatcher.utter_message(
                text="That doesn't look like a date. Please enter a valid date (e.g., '8 may', 'tomorrow')."
            )
            return {"check_out_date": None}

    def validate_number_of_guests(
        self,
        value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validate number of guests - CONTEXT AWARE"""
        
        # CRITICAL FIX: Only validate when form is asking for number of guests
        # This prevents "5555" (rejected date) from being used as number of guests
        requested_slot = tracker.get_slot("requested_slot")
        latest_intent = tracker.latest_message.get('intent', {}).get('name')
        
        # Only process if:
        # 1. Form is specifically asking for number_of_guests, OR
        # 2. It's from the initial book_hotel intent
        if requested_slot != "number_of_guests" and latest_intent != "book_hotel":
            return {"number_of_guests": tracker.slots.get("number_of_guests")}
        
        if value is None or (isinstance(value, str) and len(value.strip()) == 0):
            dispatcher.utter_message(text="Please enter the number of guests.")
            return {"number_of_guests": None}
        
        if isinstance(value, str):
            value_clean = value.strip().lower()
            
            if value_clean.isalpha() and value_clean not in [
                'one', 'two', 'three', 'four', 'five',
                'six', 'seven', 'eight', 'nine', 'ten'
            ]:
                dispatcher.utter_message(
                    text="That doesn't look like a number. Please enter the number of guests (e.g., '2', 'three')."
                )
                return {"number_of_guests": None}
        
        try:
            word_to_num = {
                "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
            }
            
            if isinstance(value, str):
                value_lower = value.lower().strip()
                if value_lower in word_to_num:
                    guests = word_to_num[value_lower]
                else:
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
    """Store the initial booking message and extract all available information"""
    
    def name(self) -> Text:
        return "action_store_initial_message"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        latest_message = tracker.latest_message.get('text', '')
        entities = tracker.latest_message.get('entities', [])
        
        slots_to_set = [SlotSet("initial_message", latest_message)]
        
        validator = ValidateHotelBookingForm()
        
        # Try to extract date range from message (e.g., "from 3 may to 5 may")
        date_range = validator.extract_date_range(latest_message)
        
        if date_range:
            # Found date range like "from 3 may to 5 may" or "10th to 12th"
            slots_to_set.append(SlotSet("check_in_date", date_range.get("check_in_date")))
            slots_to_set.append(SlotSet("check_out_date", date_range.get("check_out_date")))
            
            dispatcher.utter_message(
                text=f"📅 Dates captured: {date_range.get('check_in_date')} to {date_range.get('check_out_date')}"
            )
        else:
            # Fallback: extract individual date entities
            date_entities = [e for e in entities if e['entity'] == 'date']
            
            if len(date_entities) >= 2:
                # Two separate date entities found
                check_in = validator.parse_date(date_entities[0]['value'])
                check_out = validator.parse_date(date_entities[1]['value'])
                
                slots_to_set.append(SlotSet("check_in_date", check_in))
                slots_to_set.append(SlotSet("check_out_date", check_out))
                
                dispatcher.utter_message(
                    text=f"📅 Dates captured: {check_in} to {check_out}"
                )
            elif len(date_entities) == 1:
                # Only one date found - use as check-in
                check_in = validator.parse_date(date_entities[0]['value'])
                slots_to_set.append(SlotSet("check_in_date", check_in))
        
        return slots_to_set