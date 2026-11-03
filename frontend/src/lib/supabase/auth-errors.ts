// Public messages must not reveal whether an email exists in Supabase.
export function authErrorMessage(error: { code?: string; message: string }): string {
  switch (error.code) {
    case "invalid_credentials":
      return "The email or password is incorrect. Use your confirmed SmartNest sign-in account, or select Forgot your password. A Django admin password is separate from your website password.";
    case "email_not_confirmed":
      return "Confirm your email using the signup link before signing in.";
    case "email_address_invalid":
      return "Enter a valid email address that you can receive confirmation messages at.";
    case "email_address_not_authorized":
      return "Email delivery is not configured for this recipient. Ask the administrator to configure the email service.";
    case "signup_service_unavailable":
      return "Account creation cannot reach the sign-in service. Please try again shortly.";
    case "over_email_send_rate_limit":
      return "Confirmation emails are temporarily limited. Check your inbox before retrying later. If this continues, contact the administrator.";
    case "over_request_rate_limit":
      return "Too many requests. Wait a few minutes before trying again.";
    case "signup_disabled":
    case "email_provider_disabled":
      return "Account registration is unavailable. Contact the administrator.";
    default:
      return error.message;
  }
}
