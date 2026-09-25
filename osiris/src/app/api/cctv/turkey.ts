import type { CctvCamera } from './types';

// Turkey cameras temporarily removed due to Windy.com iframe embed restrictions (X-Frame-Options blocks).
const TURKEY_CAMERAS: CctvCamera[] = [];

export async function fetchTurkeyCameras(): Promise<CctvCamera[]> {
  return TURKEY_CAMERAS;
}

export default TURKEY_CAMERAS;
