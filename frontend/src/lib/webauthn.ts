"use client";

import { apiFetch } from "@/lib/api";

// WebAuthn's JSON serialization (what the backend's options_to_json /
// verify_* helpers both speak) represents every raw-byte field as base64url
// text (RFC 4648 §5, unpadded), while the actual browser APIs
// (navigator.credentials.create/get, and the PublicKeyCredential they
// return) want/produce real ArrayBuffers for those same fields. These two
// small helpers are the only place that boundary gets crossed.
function bufferToBase64url(buffer: ArrayBuffer): string {
  let binary = "";
  for (const byte of new Uint8Array(buffer)) binary += String.fromCharCode(byte);
  return window.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64urlToBuffer(base64url: string): ArrayBuffer {
  const padded = base64url.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (base64url.length % 4)) % 4);
  const binary = window.atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

export function isPasskeySupported(): boolean {
  return typeof window !== "undefined" && typeof window.PublicKeyCredential !== "undefined";
}

export interface PasskeyOut {
  id: string;
  device_label: string | null;
  created_at: string;
  last_used_at: string | null;
}

interface CredentialDescriptorJSON {
  id: string;
  type: "public-key";
  transports?: AuthenticatorTransport[];
}

interface RegistrationOptionsJSON {
  rp: { name: string; id: string };
  user: { id: string; name: string; displayName: string };
  challenge: string;
  pubKeyCredParams: PublicKeyCredentialParameters[];
  timeout?: number;
  excludeCredentials?: CredentialDescriptorJSON[];
  authenticatorSelection?: AuthenticatorSelectionCriteria;
  attestation?: AttestationConveyancePreference;
}

interface AuthenticationOptionsJSON {
  challenge: string;
  timeout?: number;
  rpId?: string;
  allowCredentials?: CredentialDescriptorJSON[];
  userVerification?: UserVerificationRequirement;
}

export interface PasskeyTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

/** Runs a full "add a passkey to my account" ceremony: fetch options from
 * the backend, prompt the platform authenticator via navigator.credentials.
 * create(), then hand the result back for verification. Requires an
 * existing session (the options endpoint is authenticated) -- this is not a
 * signup flow. */
export async function registerPasskey(deviceLabel?: string): Promise<PasskeyOut> {
  if (!isPasskeySupported()) throw new Error("Passkeys aren't supported in this browser.");

  const options = await apiFetch<RegistrationOptionsJSON>("/auth/passkeys/register/options", { method: "POST" });
  const publicKey: PublicKeyCredentialCreationOptions = {
    ...options,
    challenge: base64urlToBuffer(options.challenge),
    user: { ...options.user, id: base64urlToBuffer(options.user.id) },
    excludeCredentials: (options.excludeCredentials ?? []).map((c) => ({ ...c, id: base64urlToBuffer(c.id) })),
  };

  const credential = (await navigator.credentials.create({ publicKey })) as PublicKeyCredential | null;
  if (!credential) throw new Error("Passkey creation was cancelled.");
  const response = credential.response as AuthenticatorAttestationResponse;

  return apiFetch<PasskeyOut>("/auth/passkeys/register/verify", {
    method: "POST",
    body: JSON.stringify({
      credential: {
        id: credential.id,
        rawId: bufferToBase64url(credential.rawId),
        type: credential.type,
        clientExtensionResults: credential.getClientExtensionResults(),
        response: {
          clientDataJSON: bufferToBase64url(response.clientDataJSON),
          attestationObject: bufferToBase64url(response.attestationObject),
        },
      },
      device_label: deviceLabel || null,
    }),
  });
}

/** Runs a full "sign in with a passkey" ceremony for an anonymous visitor --
 * no session required, this is an alternative to a password POST /auth/login.
 * Returns the same token shape login() does; the caller is responsible for
 * storing them (see login/page.tsx). */
export async function loginWithPasskey(email: string, deviceLabel?: string): Promise<PasskeyTokenResponse> {
  if (!isPasskeySupported()) throw new Error("Passkeys aren't supported in this browser.");

  const options = await apiFetch<AuthenticationOptionsJSON>("/auth/passkeys/login/options", {
    method: "POST", auth: false, body: JSON.stringify({ email }),
  });
  const publicKey: PublicKeyCredentialRequestOptions = {
    ...options,
    challenge: base64urlToBuffer(options.challenge),
    allowCredentials: (options.allowCredentials ?? []).map((c) => ({ ...c, id: base64urlToBuffer(c.id) })),
  };

  const credential = (await navigator.credentials.get({ publicKey })) as PublicKeyCredential | null;
  if (!credential) throw new Error("Passkey sign-in was cancelled.");
  const response = credential.response as AuthenticatorAssertionResponse;

  return apiFetch<PasskeyTokenResponse>("/auth/passkeys/login/verify", {
    method: "POST",
    auth: false,
    body: JSON.stringify({
      email,
      device_label: deviceLabel || null,
      credential: {
        id: credential.id,
        rawId: bufferToBase64url(credential.rawId),
        type: credential.type,
        clientExtensionResults: credential.getClientExtensionResults(),
        response: {
          clientDataJSON: bufferToBase64url(response.clientDataJSON),
          authenticatorData: bufferToBase64url(response.authenticatorData),
          signature: bufferToBase64url(response.signature),
          userHandle: response.userHandle ? bufferToBase64url(response.userHandle) : undefined,
        },
      },
    }),
  });
}
