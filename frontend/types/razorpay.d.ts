interface RazorpayOptions {
  key?: string;
  subscription_id?: string;
  name?: string;
  description?: string;
  theme?: { color?: string };
  handler?: (response: {
    razorpay_payment_id: string;
    razorpay_subscription_id: string;
    razorpay_signature: string;
  }) => void;
  modal?: { ondismiss?: () => void };
  prefill?: { name?: string; email?: string };
}

interface RazorpayInstance {
  open: () => void;
}

declare interface Window {
  Razorpay?: new (options: RazorpayOptions) => RazorpayInstance;
}