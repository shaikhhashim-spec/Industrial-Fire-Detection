import { describe, it, expect } from 'vitest';
import {
  buildQuery,
  parseWkt,
  mapRecord,
  fetchUtahCameras,
  type UtahCameraRecord,
} from './utah';

// A representative row from /List/GetData/Cameras
const sampleRecord: UtahCameraRecord = {
  id: 112731,
  location: 'Freedom Blvd / 200 W @ 1100 N, PVO',
  roadway: 'Unknown',
  latLng: { geography: { wellKnownText: 'POINT (-111.66204 40.24863)' } },
  images: [{ imageUrl: '/map/Cctv/112731', blocked: false, disabled: false }],
};

describe('parseWkt', () => {
  it('parses POINT (lng lat) into coordinates', () => {
    expect(parseWkt('POINT (-111.66204 40.24863)')).toEqual({
      lng: -111.66204,
      lat: 40.24863,
    });
  });

  it('tolerates extra whitespace', () => {
    expect(parseWkt('POINT(  -111.5   40.7 )')).toEqual({ lng: -111.5, lat: 40.7 });
  });

  it('returns null for missing/invalid input', () => {
    expect(parseWkt(undefined)).toBeNull();
    expect(parseWkt(null)).toBeNull();
    expect(parseWkt('')).toBeNull();
    expect(parseWkt('LINESTRING (1 2, 3 4)')).toBeNull();
  });
});

describe('buildQuery', () => {
  it('encodes the DataTables query with the given paging', () => {
    const decoded = JSON.parse(decodeURIComponent(buildQuery(200, 100)));
    expect(decoded.start).toBe(200);
    expect(decoded.length).toBe(100);
    expect(decoded.order).toEqual([{ column: 1, dir: 'asc' }]);
    expect(decoded.search).toEqual({ value: '' });
  });
});

describe('mapRecord', () => {
  it('maps a valid record to a CctvCamera', () => {
    const cam = mapRecord(sampleRecord);
    expect(cam).toEqual({
      id: 'udot-112731',
      lat: 40.24863,
      lng: -111.66204,
      name: 'Freedom Blvd / 200 W @ 1100 N, PVO',
      city: 'Utah',
      country: 'US',
      feed_url: 'https://prod-ut.ibi511.com/map/Cctv/112731',
      source: 'UDOT',
    });
  });

  it('falls back to roadway then a default name', () => {
    expect(
      mapRecord({ ...sampleRecord, location: null, roadway: 'I-15 NB' })?.name,
    ).toBe('I-15 NB');
    expect(
      mapRecord({ ...sampleRecord, location: null, roadway: null })?.name,
    ).toBe('UDOT Traffic Camera');
  });

  it('skips blocked, disabled, or imageless cameras', () => {
    expect(mapRecord({ ...sampleRecord, images: [{ blocked: true }] })).toBeNull();
    expect(mapRecord({ ...sampleRecord, images: [{ disabled: true }] })).toBeNull();
    expect(mapRecord({ ...sampleRecord, images: [] })).toBeNull();
    expect(mapRecord({ ...sampleRecord, images: null })).toBeNull();
  });

  it('skips records without parseable coordinates', () => {
    expect(mapRecord({ ...sampleRecord, latLng: null })).toBeNull();
    expect(
      mapRecord({ ...sampleRecord, latLng: { geography: { wellKnownText: 'bad' } } }),
    ).toBeNull();
  });

  it('drops coordinates outside the Utah bounding box', () => {
    // London — well outside Utah
    expect(
      mapRecord({
        ...sampleRecord,
        latLng: { geography: { wellKnownText: 'POINT (-0.1276 51.5072)' } },
      }),
    ).toBeNull();
  });
});

// Live integration test — opt in with RUN_LIVE_TESTS=1 (hits the real UDOT endpoint).
const liveIt = process.env.RUN_LIVE_TESTS === '1' ? it : it.skip;

describe('fetchUtahCameras (live)', () => {
  liveIt('fetches a large set of well-formed Utah cameras', async () => {
    const cams = await fetchUtahCameras();
    expect(cams.length).toBeGreaterThan(1000);

    // No duplicate ids
    expect(new Set(cams.map((c) => c.id)).size).toBe(cams.length);

    for (const cam of cams) {
      expect(cam.id).toMatch(/^udot-\d+$/);
      expect(cam.country).toBe('US');
      expect(cam.source).toBe('UDOT');
      expect(cam.feed_url).toMatch(/^https:\/\/prod-ut\.ibi511\.com\/map\/Cctv\/\d+$/);
      expect(cam.lat).toBeGreaterThan(36.9);
      expect(cam.lat).toBeLessThan(42.1);
      expect(cam.lng).toBeGreaterThan(-114.2);
      expect(cam.lng).toBeLessThan(-108.9);
    }
  });
});
