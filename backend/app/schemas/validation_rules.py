import re

COMPANY_NAME_PATTERN = re.compile(r'[A-Za-z0-9 ]+')
GSTIN_PATTERN = re.compile(r'[A-Z0-9]{15}')
STATE_CODE_PATTERN = re.compile(r'\d{2}')
BANK_NAME_PATTERN = re.compile(r'[A-Za-z ]+')
BRANCH_PATTERN = re.compile(r'[A-Za-z0-9 ]+')
EMAIL_PATTERN = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
ACCOUNT_NUMBER_PATTERN = re.compile(r'\d{6,34}')
IFSC_PATTERN = re.compile(r'[A-Z0-9]{11}')

INDIAN_STATES_AND_UTS: tuple[tuple[str, str], ...] = (
    ('Jammu and Kashmir', '01'),
    ('Himachal Pradesh', '02'),
    ('Punjab', '03'),
    ('Chandigarh', '04'),
    ('Uttarakhand', '05'),
    ('Haryana', '06'),
    ('Delhi', '07'),
    ('Rajasthan', '08'),
    ('Uttar Pradesh', '09'),
    ('Bihar', '10'),
    ('Sikkim', '11'),
    ('Arunachal Pradesh', '12'),
    ('Nagaland', '13'),
    ('Manipur', '14'),
    ('Mizoram', '15'),
    ('Tripura', '16'),
    ('Meghalaya', '17'),
    ('Assam', '18'),
    ('West Bengal', '19'),
    ('Jharkhand', '20'),
    ('Odisha', '21'),
    ('Chhattisgarh', '22'),
    ('Madhya Pradesh', '23'),
    ('Gujarat', '24'),
    ('Maharashtra', '27'),
    ('Karnataka', '29'),
    ('Goa', '30'),
    ('Lakshadweep', '31'),
    ('Kerala', '32'),
    ('Tamil Nadu', '33'),
    ('Puducherry', '34'),
    ('Andaman and Nicobar Islands', '35'),
    ('Telangana', '36'),
    ('Andhra Pradesh', '37'),
    ('Ladakh', '38'),
    ('Dadra and Nagar Haveli and Daman and Diu', '26'),
)

STATE_CODE_BY_NAME = {name.lower(): code for name, code in INDIAN_STATES_AND_UTS}
STATE_NAME_BY_LOWERCASE = {name.lower(): name for name, _ in INDIAN_STATES_AND_UTS}


def strip_required(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f'{field_name} is required.')
    return cleaned


def validate_required_gstin(value: str) -> str:
    normalized = strip_required(value, 'GST/IN Number').upper()
    if not GSTIN_PATTERN.fullmatch(normalized):
        raise ValueError('GST/IN Number should be exactly 15 alphanumeric characters.')
    return normalized


def validate_optional_gstin(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    normalized = cleaned.upper()
    if not GSTIN_PATTERN.fullmatch(normalized):
        raise ValueError('GST/IN Number should be exactly 15 alphanumeric characters.')
    return normalized
