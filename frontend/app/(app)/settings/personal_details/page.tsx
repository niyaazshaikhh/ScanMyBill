'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';

export const dynamic = "force-dynamic";

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useAuthGuard } from '@/hooks/useAuthGuard';
import { apiRequest } from '@/lib/api';
import {
  INDIAN_STATES_AND_UTS,
  getStateCodeByName,
  sanitizeAccountNumberInput,
  sanitizeAddressInput,
  sanitizeBankNameInput,
  sanitizeBranchInput,
  sanitizeCompanyNameInput,
  sanitizeGstinInput,
  sanitizeIfscInput,
  sanitizeStateCodeInput,
  validateAccountNumber,
  validateAddress,
  validateBankName,
  validateBranch,
  validateCompanyName,
  validateEmail,
  validateIfscCode,
  validateRequiredGstin,
  validateStateAndCodePair,
  validateStateCode,
  validateStateName
} from '@/lib/validation/business-details';

type PersonalDetailsResponse = {
  company_name: string | null;
  gstin_number: string | null;
  address: string | null;
  state_name: string | null;
  state_code: string | null;
  gst_filing_period: string | null;
  email: string | null;
  bank_name: string | null;
  account_number: string | null;
  branch: string | null;
  ifsc_code: string | null;
  updated_at: string | null;
};

type PersonalDetailsForm = {
  company_name: string;
  gstin_number: string;
  address: string;
  state_name: string;
  state_code: string;
  gst_filing_period: string;
  email: string;
  bank_name: string;
  account_number: string;
  branch: string;
  ifsc_code: string;
};

const EMPTY_FORM: PersonalDetailsForm = {
  company_name: '',
  gstin_number: '',
  address: '',
  state_name: '',
  state_code: '',
  gst_filing_period: '',
  email: '',
  bank_name: '',
  account_number: '',
  branch: '',
  ifsc_code: ''
};

function normalizeForm(form: PersonalDetailsForm): PersonalDetailsForm {
  const normalizedStateName = form.state_name.trim();
  const normalizedStateCode = getStateCodeByName(normalizedStateName) || sanitizeStateCodeInput(form.state_code);

  return {
    company_name: sanitizeCompanyNameInput(form.company_name).trim(),
    gstin_number: sanitizeGstinInput(form.gstin_number),
    address: sanitizeAddressInput(form.address).trim(),
    state_name: normalizedStateName,
    state_code: normalizedStateCode,
    gst_filing_period: form.gst_filing_period.trim().toLowerCase(),
    email: form.email.trim().toLowerCase(),
    bank_name: sanitizeBankNameInput(form.bank_name).trim(),
    account_number: sanitizeAccountNumberInput(form.account_number),
    branch: sanitizeBranchInput(form.branch).trim(),
    ifsc_code: sanitizeIfscInput(form.ifsc_code)
  };
}

function validateGstFilingPeriod(value: string): string | null {
  const normalized = value.trim().toLowerCase();
  if (!normalized) return 'GST Filing Period is required.';
  if (!['monthly', 'quarterly'].includes(normalized)) {
    return 'GST Filing Period should be either monthly or quarterly.';
  }
  return null;
}

function getFieldErrors(form: PersonalDetailsForm) {
  const stateAndCodeError = validateStateAndCodePair(form.state_name, form.state_code);
  return {
    company_name: validateCompanyName(form.company_name),
    gstin_number: validateRequiredGstin(form.gstin_number),
    address: validateAddress(form.address),
    state_name: validateStateName(form.state_name),
    state_code: validateStateCode(form.state_code) || stateAndCodeError,
    gst_filing_period: validateGstFilingPeriod(form.gst_filing_period),
    email: validateEmail(form.email),
    bank_name: validateBankName(form.bank_name),
    account_number: validateAccountNumber(form.account_number),
    branch: validateBranch(form.branch),
    ifsc_code: validateIfscCode(form.ifsc_code)
  };
}

export default function PersonalDetailsPage() {
  useAuthGuard();

  const companyNameInputRef = useRef<HTMLInputElement | null>(null);
  const [form, setForm] = useState<PersonalDetailsForm>(EMPTY_FORM);
  const [savedForm, setSavedForm] = useState<PersonalDetailsForm>(EMPTY_FORM);
  const [hasSavedDetails, setHasSavedDetails] = useState(false);
  const [isEditing, setIsEditing] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fieldErrors = useMemo(() => getFieldErrors(form), [form]);
  const canSave = isEditing && !saving && Object.values(fieldErrors).every((fieldError) => !fieldError);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const details = await apiRequest<PersonalDetailsResponse>('/users/personal-details');
        const loadedStateName = (details.state_name || '').trim();
        const loadedStateCode = getStateCodeByName(loadedStateName) || (details.state_code || '');
        const loadedForm: PersonalDetailsForm = {
          company_name: details.company_name || '',
          gstin_number: details.gstin_number || '',
          address: details.address || '',
          state_name: loadedStateName,
          state_code: loadedStateCode,
          gst_filing_period: details.gst_filing_period || '',
          email: details.email || '',
          bank_name: details.bank_name || '',
          account_number: details.account_number || '',
          branch: details.branch || '',
          ifsc_code: details.ifsc_code || ''
        };
        const normalizedLoadedForm = normalizeForm(loadedForm);
        const hasCompleteDetails = Object.values(normalizedLoadedForm).every(
          (value) => value.trim().length > 0
        );

        setForm(normalizedLoadedForm);
        setSavedForm(normalizedLoadedForm);
        setHasSavedDetails(hasCompleteDetails);
        setIsEditing(!hasCompleteDetails);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load personal details');
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, []);

  const onSave = async () => {
    setMessage(null);
    setError(null);

    const normalizedForm = normalizeForm(form);
    const normalizedErrors = getFieldErrors(normalizedForm);

    if (Object.values(normalizedErrors).some((fieldError) => fieldError)) {
      setForm(normalizedForm);
      setError('Please correct the highlighted fields before saving.');
      return;
    }

    setSaving(true);
    try {
      await apiRequest('/users/personal-details', {
        method: 'PUT',
        body: normalizedForm
      });
      setForm(normalizedForm);
      setSavedForm(normalizedForm);
      setHasSavedDetails(true);
      setIsEditing(false);
      setMessage('Personal details saved successfully.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save personal details');
    } finally {
      setSaving(false);
    }
  };

  const onEdit = () => {
    setMessage(null);
    setError(null);
    setIsEditing(true);
    setTimeout(() => {
      companyNameInputRef.current?.focus();
    }, 0);
  };

  const onCancelEdit = () => {
    setMessage(null);
    setError(null);
    setForm(savedForm);
    setIsEditing(false);
  };

  return (
    <div className='space-y-5'>
      <div>
        <h2 className='font-[var(--font-space)] text-2xl font-semibold'>Personal Details</h2>
        <p className='text-sm text-muted-foreground'>
          These details are used to infer whether uploaded bills are sales or purchase.
        </p>
      </div>

      <Card className='bg-card/85'>
        <CardHeader>
          <CardTitle>Business Identity</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className='text-sm text-muted-foreground'>Loading personal details...</p>
          ) : (
            <div className='space-y-4'>
              <div className='space-y-1'>
                <Label htmlFor='company-name'>
                  Company Name <span className='text-destructive'>*</span>
                </Label>
                <Input
                  id='company-name'
                  ref={companyNameInputRef}
                  value={form.company_name}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      company_name: sanitizeCompanyNameInput(event.target.value)
                    }))
                  }
                  maxLength={20}
                  disabled={!isEditing}
                  required
                />
                {isEditing && fieldErrors.company_name ? (
                  <p className='text-xs text-destructive'>{fieldErrors.company_name}</p>
                ) : null}
              </div>
              <div className='space-y-1'>
                <Label htmlFor='gstin-number'>
                  GST/IN Number <span className='text-destructive'>*</span>
                </Label>
                <Input
                  id='gstin-number'
                  value={form.gstin_number}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      gstin_number: sanitizeGstinInput(event.target.value)
                    }))
                  }
                  maxLength={15}
                  disabled={!isEditing}
                  required
                />
                {isEditing && fieldErrors.gstin_number ? (
                  <p className='text-xs text-destructive'>{fieldErrors.gstin_number}</p>
                ) : null}
              </div>
              <div className='space-y-1'>
                <Label htmlFor='address'>
                  Address <span className='text-destructive'>*</span>
                </Label>
                <Textarea
                  id='address'
                  value={form.address}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, address: sanitizeAddressInput(event.target.value) }))
                  }
                  maxLength={115}
                  disabled={!isEditing}
                  required
                />
                <p className='text-xs text-muted-foreground'>{form.address.length}/115</p>
                {isEditing && fieldErrors.address ? (
                  <p className='text-xs text-destructive'>{fieldErrors.address}</p>
                ) : null}
              </div>
              <div className='grid gap-4 md:grid-cols-2'>
                <div className='space-y-1'>
                  <Label htmlFor='state-name'>
                    State Name <span className='text-destructive'>*</span>
                  </Label>
                  <Select
                    id='state-name'
                    value={form.state_name}
                    onChange={(event) => {
                      const selectedStateName = event.target.value;
                      const selectedStateCode = getStateCodeByName(selectedStateName) || '';
                      setForm((prev) => ({
                        ...prev,
                        state_name: selectedStateName,
                        state_code: selectedStateCode
                      }));
                    }}
                    disabled={!isEditing}
                    required
                  >
                    <option value=''>Select State / Union Territory</option>
                    {INDIAN_STATES_AND_UTS.map((stateOption) => (
                      <option key={stateOption.name} value={stateOption.name}>
                        {stateOption.name}
                      </option>
                    ))}
                  </Select>
                  {isEditing && fieldErrors.state_name ? (
                    <p className='text-xs text-destructive'>{fieldErrors.state_name}</p>
                  ) : null}
                </div>
                <div className='space-y-1'>
                  <Label htmlFor='state-code'>
                    State Code <span className='text-destructive'>*</span>
                  </Label>
                  <Input
                    id='state-code'
                    value={form.state_code}
                    onChange={(event) =>
                      setForm((prev) => ({
                        ...prev,
                        state_code: sanitizeStateCodeInput(event.target.value)
                      }))
                    }
                    maxLength={2}
                    readOnly
                    disabled={!isEditing}
                    required
                  />
                  {isEditing && fieldErrors.state_code ? (
                    <p className='text-xs text-destructive'>{fieldErrors.state_code}</p>
                  ) : null}
                </div>
              </div>
              <div className='space-y-1'>
                <Label htmlFor='gst-filing-period'>
                  GST Filing Period <span className='text-destructive'>*</span>
                </Label>
                <Select
                  id='gst-filing-period'
                  value={form.gst_filing_period}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      gst_filing_period: event.target.value
                    }))
                  }
                  disabled={!isEditing}
                  required
                >
                  <option value=''>Select filing period</option>
                  <option value='monthly'>Monthly</option>
                  <option value='quarterly'>Quarterly</option>
                </Select>
                {isEditing && fieldErrors.gst_filing_period ? (
                  <p className='text-xs text-destructive'>{fieldErrors.gst_filing_period}</p>
                ) : null}
              </div>
              <div className='space-y-1'>
                <Label htmlFor='email'>
                  Email <span className='text-destructive'>*</span>
                </Label>
                <Input
                  id='email'
                  type='email'
                  value={form.email}
                  onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                  disabled={!isEditing}
                  required
                />
                {isEditing && fieldErrors.email ? (
                  <p className='text-xs text-destructive'>{fieldErrors.email}</p>
                ) : null}
              </div>

              <div className='border-t border-border pt-4'>
                <h3 className='font-semibold'>Bank Details</h3>
                <div className='mt-3 grid gap-4 md:grid-cols-2'>
                  <div className='space-y-1'>
                    <Label htmlFor='bank-name'>
                      Bank Name <span className='text-destructive'>*</span>
                    </Label>
                    <Input
                      id='bank-name'
                      value={form.bank_name}
                      onChange={(event) =>
                        setForm((prev) => ({
                          ...prev,
                          bank_name: sanitizeBankNameInput(event.target.value)
                        }))
                      }
                      maxLength={15}
                      disabled={!isEditing}
                      required
                    />
                    {isEditing && fieldErrors.bank_name ? (
                      <p className='text-xs text-destructive'>{fieldErrors.bank_name}</p>
                    ) : null}
                  </div>
                  <div className='space-y-1'>
                    <Label htmlFor='account-number'>
                      A/c No. <span className='text-destructive'>*</span>
                    </Label>
                    <Input
                      id='account-number'
                      value={form.account_number}
                      onChange={(event) =>
                        setForm((prev) => ({
                          ...prev,
                          account_number: sanitizeAccountNumberInput(event.target.value)
                        }))
                      }
                      maxLength={34}
                      disabled={!isEditing}
                      required
                    />
                    {isEditing && fieldErrors.account_number ? (
                      <p className='text-xs text-destructive'>{fieldErrors.account_number}</p>
                    ) : null}
                  </div>
                  <div className='space-y-1'>
                    <Label htmlFor='branch'>
                      Branch <span className='text-destructive'>*</span>
                    </Label>
                    <Input
                      id='branch'
                      value={form.branch}
                      onChange={(event) =>
                        setForm((prev) => ({
                          ...prev,
                          branch: sanitizeBranchInput(event.target.value)
                        }))
                      }
                      maxLength={15}
                      disabled={!isEditing}
                      required
                    />
                    {isEditing && fieldErrors.branch ? (
                      <p className='text-xs text-destructive'>{fieldErrors.branch}</p>
                    ) : null}
                  </div>
                  <div className='space-y-1'>
                    <Label htmlFor='ifsc-code'>
                      IFSC Code <span className='text-destructive'>*</span>
                    </Label>
                    <Input
                      id='ifsc-code'
                      value={form.ifsc_code}
                      onChange={(event) =>
                        setForm((prev) => ({
                          ...prev,
                          ifsc_code: sanitizeIfscInput(event.target.value)
                        }))
                      }
                      maxLength={11}
                      disabled={!isEditing}
                      required
                    />
                    {isEditing && fieldErrors.ifsc_code ? (
                      <p className='text-xs text-destructive'>{fieldErrors.ifsc_code}</p>
                    ) : null}
                  </div>
                </div>
              </div>

              {error ? <p className='text-sm text-destructive'>{error}</p> : null}
              {message ? <p className='text-sm text-muted-foreground'>{message}</p> : null}

              <div className='flex flex-wrap gap-2'>
                {isEditing ? (
                  <Button type='button' onClick={onSave} disabled={!canSave}>
                    {saving ? 'Saving...' : 'Save'}
                  </Button>
                ) : (
                  <Button
                    type='button'
                    onClick={(event) => {
                      event.preventDefault();
                      onEdit();
                    }}
                    disabled={saving}
                  >
                    Edit
                  </Button>
                )}
                {isEditing && hasSavedDetails ? (
                  <Button type='button' variant='outline' onClick={onCancelEdit}>
                    Cancel
                  </Button>
                ) : null}
                <Button asChild variant='outline'>
                  <Link href='/settings'>Back to Settings</Link>
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

