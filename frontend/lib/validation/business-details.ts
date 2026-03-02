export type StateOption = {
  name: string;
  code: string;
};

export const INDIAN_STATES_AND_UTS: StateOption[] = [
  { name: 'Jammu and Kashmir', code: '01' },
  { name: 'Himachal Pradesh', code: '02' },
  { name: 'Punjab', code: '03' },
  { name: 'Chandigarh', code: '04' },
  { name: 'Uttarakhand', code: '05' },
  { name: 'Haryana', code: '06' },
  { name: 'Delhi', code: '07' },
  { name: 'Rajasthan', code: '08' },
  { name: 'Uttar Pradesh', code: '09' },
  { name: 'Bihar', code: '10' },
  { name: 'Sikkim', code: '11' },
  { name: 'Arunachal Pradesh', code: '12' },
  { name: 'Nagaland', code: '13' },
  { name: 'Manipur', code: '14' },
  { name: 'Mizoram', code: '15' },
  { name: 'Tripura', code: '16' },
  { name: 'Meghalaya', code: '17' },
  { name: 'Assam', code: '18' },
  { name: 'West Bengal', code: '19' },
  { name: 'Jharkhand', code: '20' },
  { name: 'Odisha', code: '21' },
  { name: 'Chhattisgarh', code: '22' },
  { name: 'Madhya Pradesh', code: '23' },
  { name: 'Gujarat', code: '24' },
  { name: 'Dadra and Nagar Haveli and Daman and Diu', code: '26' },
  { name: 'Maharashtra', code: '27' },
  { name: 'Karnataka', code: '29' },
  { name: 'Goa', code: '30' },
  { name: 'Lakshadweep', code: '31' },
  { name: 'Kerala', code: '32' },
  { name: 'Tamil Nadu', code: '33' },
  { name: 'Puducherry', code: '34' },
  { name: 'Andaman and Nicobar Islands', code: '35' },
  { name: 'Telangana', code: '36' },
  { name: 'Andhra Pradesh', code: '37' },
  { name: 'Ladakh', code: '38' }
];

const STATE_CODE_BY_NAME = new Map(
  INDIAN_STATES_AND_UTS.map((stateOption) => [stateOption.name.toLowerCase(), stateOption.code])
);

const COMPANY_NAME_PATTERN = /^[A-Za-z0-9 ]+$/;
const GSTIN_PATTERN = /^[A-Z0-9]{15}$/;
const STATE_CODE_PATTERN = /^\d{2}$/;
const BANK_NAME_PATTERN = /^[A-Za-z ]+$/;
const BRANCH_PATTERN = /^[A-Za-z0-9 ]+$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const ACCOUNT_NUMBER_PATTERN = /^\d{6,34}$/;
const IFSC_PATTERN = /^[A-Z0-9]{11}$/;

export function sanitizeCompanyNameInput(value: string): string {
  return value.replace(/[^A-Za-z0-9 ]/g, '').slice(0, 20);
}

export function sanitizeClientNameInput(value: string): string {
  return value.replace(/[^A-Za-z0-9 ]/g, '').slice(0, 15);
}

export function sanitizeGstinInput(value: string): string {
  return value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 15);
}

export function sanitizeAddressInput(value: string): string {
  return value.slice(0, 115);
}

export function sanitizeStateCodeInput(value: string): string {
  return value.replace(/\D/g, '').slice(0, 2);
}

export function sanitizeBankNameInput(value: string): string {
  return value.replace(/[^A-Za-z ]/g, '').slice(0, 15);
}

export function sanitizeBranchInput(value: string): string {
  return value.replace(/[^A-Za-z0-9 ]/g, '').slice(0, 15);
}

export function sanitizeAccountNumberInput(value: string): string {
  return value.replace(/\D/g, '').slice(0, 34);
}

export function sanitizeIfscInput(value: string): string {
  return value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 11);
}

export function normalizeOptionalGstin(value: string): string | null {
  const normalized = value.trim().toUpperCase();
  if (!normalized) return null;
  return normalized;
}

export function validateCompanyName(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return 'Company Name is required.';
  if (!COMPANY_NAME_PATTERN.test(trimmed)) {
    return 'Company Name should be alphanumeric and special characters are not allowed.';
  }
  return null;
}

export function validateClientName(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return 'Name is required.';
  if (!COMPANY_NAME_PATTERN.test(trimmed)) {
    return 'Name should be alphanumeric and special characters are not allowed.';
  }
  return null;
}

export function validateRequiredGstin(value: string): string | null {
  const trimmed = value.trim().toUpperCase();
  if (!trimmed) return 'GST/IN Number is required.';
  if (!GSTIN_PATTERN.test(trimmed)) {
    return 'GST/IN Number should be exactly 15 alphanumeric characters.';
  }
  return null;
}

export function validateOptionalGstin(value: string): string | null {
  const normalized = normalizeOptionalGstin(value);
  if (!normalized) return null;
  if (!GSTIN_PATTERN.test(normalized)) {
    return 'GST/IN Number should be exactly 15 alphanumeric characters.';
  }
  return null;
}

export function validateAddress(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return 'Address is required.';
  if (trimmed.length > 115) return 'Address should be up to 115 characters only.';
  return null;
}

export function validateStateName(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return 'State Name is required.';
  if (!STATE_CODE_BY_NAME.has(trimmed.toLowerCase())) {
    return 'Please select a valid Indian state or union territory.';
  }
  return null;
}

export function validateStateCode(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return 'State Code is required.';
  if (!STATE_CODE_PATTERN.test(trimmed)) {
    return 'State Code should be exactly 2 digits.';
  }
  return null;
}

export function validateStateAndCodePair(stateName: string, stateCode: string): string | null {
  const expectedCode = STATE_CODE_BY_NAME.get(stateName.trim().toLowerCase());
  if (!expectedCode) return 'Please select a valid Indian state or union territory.';
  if (expectedCode !== stateCode.trim()) return 'State Code does not match selected State Name.';
  return null;
}

export function getStateCodeByName(stateName: string): string | null {
  return STATE_CODE_BY_NAME.get(stateName.trim().toLowerCase()) || null;
}

export function validateEmail(value: string): string | null {
  const trimmed = value.trim().toLowerCase();
  if (!trimmed) return 'Email is required.';
  if (!EMAIL_PATTERN.test(trimmed)) return 'Email format is invalid.';
  return null;
}

export function validateBankName(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return 'Bank Name is required.';
  if (!BANK_NAME_PATTERN.test(trimmed)) return 'Bank Name should contain only alphabets.';
  return null;
}

export function validateAccountNumber(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return 'A/c No. is required.';
  if (!ACCOUNT_NUMBER_PATTERN.test(trimmed)) {
    return 'A/c No. should contain only digits (6 to 34 digits).';
  }
  return null;
}

export function validateBranch(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return 'Branch is required.';
  if (!BRANCH_PATTERN.test(trimmed)) {
    return 'Branch should contain only letters, numbers, and spaces.';
  }
  return null;
}

export function validateIfscCode(value: string): string | null {
  const trimmed = value.trim().toUpperCase();
  if (!trimmed) return 'IFSC Code is required.';
  if (!IFSC_PATTERN.test(trimmed)) {
    return 'IFSC Code should be an 11-character alphanumeric code.';
  }
  return null;
}
