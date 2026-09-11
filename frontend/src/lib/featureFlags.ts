/**
 * Camera-based face proctoring is unreliable across browsers/devices
 * (site permission vs. OS-level camera privacy settings, camera-in-use
 * conflicts) and isn't worth the risk of blocking a live exam right
 * before a presentation. Flip this back to true once it's been hardened
 * and tested across the devices students actually use.
 */
export const FACE_PROCTORING_ENABLED = false;
