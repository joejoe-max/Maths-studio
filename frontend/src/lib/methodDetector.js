/**
 * methodDetector.js — DEPRECATED
 *
 * Domain detection and method selection have been moved entirely to the backend
 * (/api/compute/analyze) per the architecture spec: the frontend must never
 * detect math structure, choose methods, or interpret engineering meaning.
 *
 * This file is kept as an empty stub to avoid breaking any stale imports.
 */

export function detectDomain() { return null; }
export function getMethodsForDomain() { return []; }
export function shouldShowMethodPopup() { return false; }
