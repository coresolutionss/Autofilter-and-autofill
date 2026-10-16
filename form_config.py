"""Local form definitions based on the supplied AMB reference forms.
Signature fields are represented by preparation details, never an electronic signature.
"""

def section(title, fields):
    return (title, [(key, label) for key, label in fields])


def address(prefix, label):
    return [(f"{prefix}_{key}", f"{label} {text}") for key, text in (
        ("address", "address"), ("unit", "suite / unit / shop"), ("city", "city"),
        ("state", "state / province"), ("postal_code", "postal code"), ("country", "country"))]


COMPANY = [("company_name", "Company legal name"), ("registration_state", "State / country registered"),
           ("trade_name", "DBA / trade name"), ("business_phone", "Business telephone"),
           ("business_fax", "Business fax"), ("business_email", "Business email")]
ACCOUNT_SECTIONS = [
    section("Business", [("entity_type", "Entity type (corporation / partnership / individual / other)"),
        ("company_name", "Company legal name"), ("business_start_date", "Business start date"),
        ("trade_name", "DBA / trade name"), ("business_phone", "Business telephone"),
        ("business_fax", "Business fax"), ("business_email", "Business email"),
        ("preferred_language", "Preferred language")] + address("business", "Business")),
    section("Shipping", [("shipping_type", "Shipping address type (residential / commercial)"),
        ("shipping_same_as_business", "Same as business address? (yes / no)")] + address("shipping", "Shipping")),
    section("Tax and lease", [("tax_id", "Federal / national tax ID"), ("tax_country", "Tax ID country"),
        ("resale_tax_id", "Resale tax ID"), ("jbt_id", "JBT ID"), ("dnb_number", "DNB number"),
        ("lease_holder", "Name on store lease"), ("certificate_number", "Sales tax certificate number"),
        ("certificate_state", "Certificate state / region"), ("certificate_by", "Certificate representative name")]),
    section("Owner identity", [("full_name", "Owner full name as printed (confirm name split below)"), ("first_name", "Owner given names"), ("middle_name", "Owner middle names"),
        ("last_name", "Owner surname"), ("date_of_birth", "Owner date of birth"),
        ("license_number", "Driver license number"), ("id_number", "National / state ID number"),
        ("passport_number", "Passport number"), ("issuing_country", "Identity document issuing country"),
        ("nationality", "Nationality"), ("expiration_date", "Identity document expiration date"),
        ("curp", "Mexico CURP"), ("elector_key", "Mexico INE elector key"),
        ("ssn", "Owner SS number (if applicable)"), ("home_phone", "Home telephone"),
        ("cell_phone", "Cell phone")] + address("home", "Home")),
    section("Spouse", [("spouse_first_name", "Spouse given names"), ("spouse_last_name", "Spouse surname"),
        ("spouse_ssn", "Spouse SS number (if applicable)"), ("spouse_license_number", "Spouse driver license number"),
        ("spouse_passport_number", "Spouse passport number")]),
    section("Authorized buyers", [(f"buyer_{i}", f"Authorized buyer {i}") for i in range(1, 4)]),
    section("Trade references", [(f"trade_{i}_{key}", f"Reference {i}: {label}") for i in range(1, 5)
        for key, label in [("company", "company name"), ("contact", "contact person"),
            ("email_fax", "email / fax"), ("account", "account number")]]),
    section("Personal references", [(f"personal_{i}_{key}", f"Reference {i}: {label}") for i in range(1, 4)
        for key, label in [("name", "name"), ("phone", "contact number")]]),
    section("Bank reference", [("bank_name", "Bank name"), ("bank_officer", "Account officer name"),
        ("bank_address", "Bank address"), ("bank_phone", "Bank telephone"),
        ("bank_account_number", "Bank account number"), ("bank_account_name", "Name on bank account"),
        ("bank_opening_date", "Account opening date"), ("bank_authorization_date", "Bank authorization date")]),
    section("Signing preparation", [("principal_print_name", "Principal printed name"), ("principal_title", "Principal title"),
        ("second_print_name", "Second partner / co-owner printed name"), ("second_title", "Second partner title"),
        ("prepared_date", "Prepared date (signatures collected separately)")]),
    section("Copies provided", [("copy_driver_license", "Copy of driver license (yes / no)"),
        ("copy_sales_tax_permit", "Copy of sales tax permit (yes / no)"),
        ("copy_lease_agreement", "Copy of lease agreement (yes / no)")]),
    section("Office use", [("date_received", "Date received"), ("jbt_rating", "JBT rating"),
        ("credit_terms", "Credit terms"), ("credit_limit", "Credit limit"),
        ("discount_special", "Special discount rate"), ("discount_regular", "Regular discount rate"),
        ("date_approved", "Date approved"), ("approved_by", "Approved by"), ("sales_associate", "Sales associate")]),
]
CHANGE_FIELDS = COMPANY + address("physical", "Physical") + address("mailing", "Mailing") + address("shipping", "Shipping")
CHANGE_SECTIONS = [
    section("Account and owner", [("account_number", "Current account number"), ("first_name", "Owner given names"),
        ("last_name", "Owner surname"), ("entity_type", "Entity type"), ("change_reason", "Reason / description of change"),
        ("signed_date", "Date beside signature (signatures collected separately)")]),
    section("On record information", [("old_" + k, v) for k, v in CHANGE_FIELDS]),
    section("New information", [("new_" + k, v) for k, v in CHANGE_FIELDS]),
    section("Office use", [("credit_terms", "Credit terms"), ("credit_limit", "Credit limit"),
        ("discount_special", "Special discount rate"), ("discount_regular", "Regular discount rate"),
        ("approved_by", "Approved by"), ("updated_by", "Information updated by"), ("updated_date", "Updated date")]),
]
FORMS = {
    "new_account": {"title": "New Account Application", "sections": ACCOUNT_SECTIONS,
        "required": ["company_name", "first_name", "last_name", "tax_id"]},
    "information_change": {"title": "Customer Information Change", "sections": CHANGE_SECTIONS,
        "required": ["account_number", "first_name", "last_name", "change_reason"]},
}
DOCUMENT_KINDS = {
    "drivers_license": "Driver license (any country)", "id_card": "National / state ID card (any country)",
    "passport": "Passport", "tax_document": "Federal / national tax document",
    "sales_tax_permit": "Sales tax permit", "lease": "Lease agreement", "supporting": "Other supporting document",
}
IDENTITY_KINDS = {"drivers_license", "id_card", "passport"}

def field_labels(form_type):
    return {key: label for _, fields in FORMS[form_type]["sections"] for key, label in fields}
