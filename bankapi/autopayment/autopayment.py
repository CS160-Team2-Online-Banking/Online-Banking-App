from bankapi.models import *
from django.db import transaction
from datetime import datetime
import re


class AutopaymentBuilder:

    @staticmethod
    @transaction.atomic
    def build_autopayment(decrypted_auth_token, payment_data):
        owner_id = decrypted_auth_token["user_id"]
        payment_schedule_data = payment_data["payment_schedule_data"]
        from_account_id = payment_data["from_account_id"]
        from_account_no = payment_data["from_account_no"]
        to_account_id = payment_data["to_account_id"]
        to_account_no = payment_data["to_account_no"]
        transfer_amount = payment_data["transfer_amount"]
        transfer_type = payment_data["transfer_type"]

        if ((from_account_id is None and from_account_no is None) or
           (to_account_id is None and to_account_no is None)):
            return None

        owner = Customer.objects.filter(pk=owner_id).first()
        if owner is None:
            return None  # TODO: handle this, raise an exception or something

        if from_account_id is not None:
            from_account = Accounts.objects.filter(pk=from_account_id).first()
        else:
            from_account = Accounts.objects.filter(account_number=from_account_no)

        if from_account is None:
            return None  # TODO: handle this, raise an exception or something

        if transfer_type == TransferTypes.EXTERN:
            account_model = ExternalAccount
        else:
            account_model = Accounts
            transfer_type = TransferTypes.U_TO_U

        if to_account_id is not None:
            to_account = account_model.objects.filter(pk=to_account_id).first()
        else:
            to_account = account_model.objects.filter(account_number=to_account_no).first()
        if to_account is None:
            return None  # TODO: handle this, raise an exception or something


        # if all accounts associated with this account exist, and the user is authorized to setup transfers
        if from_account.owner_id == owner.pk:
            payment_frequency = payment_schedule_data["payment_frequency"]
            start_date = payment_schedule_data["start_date"]
            end_date = payment_schedule_data["end_date"]

            if not PaymentFrequencies.validate_string(payment_frequency):
                return None  # TODO: handle this, raise an exception or something

            payment_schedule = PaymentSchedules(start_date=start_date,
                                                end_date=end_date,
                                                payment_frequency=payment_frequency)
            payment_schedule.save()

            other_payments = AutopaymentObjects.objects.filter(owner_user_id=owner.pk)
            all_payments = AutopaymentObjects.objects.all()
            new_id = 0 if not len(all_payments) else (all_payments.latest("id").id + 1)
            new_auto_payment_id = 0 if not len(other_payments) else (other_payments
                                                                     .latest('autopayment_id')
                                                                     .autopayment_id
                                                                     + 1)
            autopayment = AutopaymentObjects(owner_user_id=owner.pk,
                                             autopayment_id=new_auto_payment_id,
                                             payment_schedule_id=payment_schedule.pk,
                                             from_account_id=from_account.pk,
                                             to_account_id=to_account.pk,
                                             transfer_amount=transfer_amount,
                                             transfer_type=transfer_type,
                                             id=new_id)
            autopayment.save()
        return (autopayment.owner_user_id, autopayment.autopayment_id)

def is_payment_due(autopayment_obj) -> bool:
    # if the current date is less than the end date and after the start date
    payment_schedule = autopayment_obj.payment_schedule
    start_datetime = datetime.combine(payment_schedule.start_date, datetime.min.time())
    end_datetime = datetime.combine(payment_schedule.end_date, datetime.min.time())
    now_time = datetime.now()
    if start_datetime < now_time < end_datetime:
        if autopayment_obj.last_payment is None:  # if no payment has been made yet
            return True

        last_payment_date = autopayment_obj.last_payment

        if payment_schedule.payment_frequency == PaymentFrequencies.DAILY:
            return now_time.day > last_payment_date.day
        elif payment_schedule.payment_frequency == PaymentFrequencies.WEEKLY:
            #  isocalendar returns a tuple with the year[0], week number[1], and day number[2]
            return now_time.isocalendar()[1] > last_payment_date.isocalendar()[1]
        elif payment_schedule.payment_frequency == PaymentFrequencies.MONTHLY:
            return now_time.month > last_payment_date.month
        elif payment_schedule.payment_frequency == PaymentFrequencies.YEARLY:
            return now_time.year > last_payment_date.year
    return False
