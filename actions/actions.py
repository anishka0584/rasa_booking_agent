from typing import Any, Text, Dict, List
from rasa_sdk import Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet


class ValidateHotelBookingForm(FormValidationAction):

    def name(self) -> Text:
        return "validate_hotel_booking_form"

    def validate_city(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        return {"city": value}

    def validate_check_in_date(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        # Only set check_in_date, don't touch check_out_date
        return {"check_in_date": value}

    def validate_check_out_date(
        self,
        value: Text,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        # Only set check_out_date, don't touch check_in_date
        return {"check_out_date": value}

    def validate_number_of_guests(
        self,
        value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        return {"number_of_guests": value}