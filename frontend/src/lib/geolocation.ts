export type Coords = { lat: number; lng: number };

export class GeolocationUnsupportedError extends Error {}
export class GeolocationDeniedError extends Error {}
/** El backend solo acepta lat 5–7 y lng -76 a -74 (Valle de Aburrá). */
export class OutsideMedellinError extends Error {}

const BOUNDS = { latMin: 5, latMax: 7, lngMin: -76, lngMax: -74 };

export function isInsideMedellin({ lat, lng }: Coords): boolean {
  return lat >= BOUNDS.latMin && lat <= BOUNDS.latMax && lng >= BOUNDS.lngMin && lng <= BOUNDS.lngMax;
}

export function requestCurrentPosition(timeoutMs = 10000): Promise<Coords> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      reject(new GeolocationUnsupportedError());
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) =>
        resolve({ lat: position.coords.latitude, lng: position.coords.longitude }),
      () => reject(new GeolocationDeniedError()),
      { enableHighAccuracy: false, timeout: timeoutMs, maximumAge: 5 * 60 * 1000 },
    );
  });
}
