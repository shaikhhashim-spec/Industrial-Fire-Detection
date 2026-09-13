import type { CctvCamera } from './types';

/**
 * Japan CCTV Cameras
 * Sources:
 *  - YouTube 24/7 live streams (Shibuya, Tokyo Tower, Mt. Fuji, etc.)
 *  - Japan MLIT River Monitoring (cam.river.go.jp) — Tokyo/Yokohama area
 *  - Known public webcams across Japan
 */

const JAPAN_CAMERAS: CctvCamera[] = [
  // ── YouTube Live Streams ──
  {
    id: 'jp-shibuya-crossing',
    lat: 35.6595, lng: 139.7005,
    name: 'Shibuya Scramble Crossing',
    city: 'Tokyo', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/coYw-eVU0Ks?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'ANN News / YouTube',
  },
  {
    id: 'jp-tokyo-tower',
    lat: 35.6586, lng: 139.7454,
    name: 'Tokyo Tower Live Cam',
    city: 'Tokyo', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/cbJ03Xk_eLQ?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-mt-fuji',
    lat: 35.3606, lng: 138.7274,
    name: 'Mt. Fuji Live',
    city: 'Shizuoka/Yamanashi', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/5aLh8R2HqOQ?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-osaka-dotonbori',
    lat: 34.6687, lng: 135.5013,
    name: 'Dotonbori Live Cam',
    city: 'Osaka', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/m6J9w94oBXY?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-shinjuku-kabukicho',
    lat: 35.6938, lng: 139.7034,
    name: 'Shinjuku Kabukicho Live',
    city: 'Tokyo', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/gFRtAAmiFbE?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-akihabara',
    lat: 35.6984, lng: 139.7731,
    name: 'Akihabara Electric Town',
    city: 'Tokyo', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/HULqEi0RqXI?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-tokyo-skytree',
    lat: 35.7101, lng: 139.8107,
    name: 'Tokyo Skytree Live',
    city: 'Tokyo', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/xIp5F2D8vQ0?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-ginza',
    lat: 35.6717, lng: 139.7649,
    name: 'Ginza 4-Chome Crossing',
    city: 'Tokyo', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/LYzCVlG6lkE?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-yokohama-port',
    lat: 35.4437, lng: 139.6380,
    name: 'Yokohama Port Live',
    city: 'Yokohama', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/dN4HRiQnAn4?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-kyoto-kiyomizu',
    lat: 34.9949, lng: 135.7850,
    name: 'Kyoto Arashiyama Bamboo Forest',
    city: 'Kyoto', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/Op-lf2NRMzs?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-hiroshima-dome',
    lat: 34.3955, lng: 132.4536,
    name: 'Hiroshima Peace Memorial',
    city: 'Hiroshima', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/R6-G_4W5K_M?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-sapporo-odori',
    lat: 43.0588, lng: 141.3563,
    name: 'Sapporo Odori Park',
    city: 'Sapporo', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/N7k3Q5rMZfM?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-naha-kokusai',
    lat: 26.3358, lng: 127.6809,
    name: 'Naha Kokusai Street',
    city: 'Naha/Okinawa', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/cKTkCqVB00A?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-fukuoka-hakata',
    lat: 33.5898, lng: 130.4017,
    name: 'Fukuoka Hakata Station',
    city: 'Fukuoka', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/xvN_GxkVjKs?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-nagoya-station',
    lat: 35.1709, lng: 136.8815,
    name: 'Nagoya Station Area',
    city: 'Nagoya', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/Oji-G0UhD9U?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-kobe-harbor',
    lat: 34.6851, lng: 135.1956,
    name: 'Kobe Harborland',
    city: 'Kobe', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/3xGw0xQBN0s?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-asakusa-sensoji',
    lat: 35.7148, lng: 139.7967,
    name: 'Asakusa Senso-ji Temple',
    city: 'Tokyo', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/Ic5FaEzh6h0?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },
  {
    id: 'jp-tokyo-bay',
    lat: 35.6279, lng: 139.7742,
    name: 'Tokyo Bay Waterfront',
    city: 'Tokyo', country: 'Japan',
    stream_url: 'https://www.youtube.com/embed/Y9X1W8HBE4g?autoplay=1&mute=1',
    stream_type: 'iframe',
    source: 'YouTube',
  },

  // ── Japan MLIT River Monitoring System (cam.river.go.jp) — Direct image feeds ──
  // These are public government cameras that refresh every ~60 seconds
  {
    id: 'jp-river-aoba-meguro', lat: 35.649111, lng: 139.693419,
    name: 'Aoba Platform, Meguro Ward', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/303329015.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-asayama-bridge', lat: 35.536928, lng: 139.498187,
    name: 'Asayama Bridge', city: 'Yokohama', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/303585018.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-atago-shirane', lat: 35.47929, lng: 139.552883,
    name: 'Atago-Shirane Bridge', city: 'Yokohama', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/303585047.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-banri-bridge', lat: 35.463406, lng: 139.622166,
    name: 'Banri Bridge, Karasido River', city: 'Yokohama', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/103585088.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-bentenjima', lat: 35.639903, lng: 139.887903,
    name: 'Bentenjima Bridge, Urayasu', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/103073090.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-expressway7', lat: 35.698164, lng: 139.859811,
    name: 'Capital Expressway 7, Arakawa', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221281005.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-denenchofu', lat: 35.582931, lng: 139.672006,
    name: 'Denenchofu Water Level Station', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/cctv_130001_31C03351.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-denenchofu-ota', lat: 35.589261, lng: 139.665769,
    name: 'Denenchofu Station, Ota Ward', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221320032.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-ebara-pond', lat: 35.627906, lng: 139.716111,
    name: 'Ebara Regulation Pond, Shinagawa', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/303329016.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-futako-tamagawa', lat: 35.610458, lng: 139.629478,
    name: 'Futako Tamagawa Rise Tower, Setagaya', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221320007.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-hachiman', lat: 35.41315, lng: 139.628097,
    name: 'Hachiman Bridge', city: 'Yokohama', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/303585121.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-heiwa', lat: 35.46374, lng: 139.588114,
    name: 'Heiwa Bridge, Karasido River', city: 'Yokohama', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/103585089.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-tamagawa-green', lat: 35.585, lng: 139.668,
    name: 'Tamagawa Green Area Office, Ota Ward', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/cctv_130001_31C03399.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-shino-bridge', lat: 35.651, lng: 139.746,
    name: 'Shī-no-Bridge, Minato Ward', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/303329013.jpg', source: 'MLIT river.go.jp',
  },
  // Additional known Tokyo river monitoring cams (MLIT cam IDs from public listings)
  {
    id: 'jp-river-edogawa-1', lat: 35.7088, lng: 139.8772,
    name: 'Edogawa River Upstream', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221281001.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-edogawa-2', lat: 35.7152, lng: 139.8690,
    name: 'Edogawa River Komatsugawa', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221281002.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-arakawa-1', lat: 35.7931, lng: 139.7195,
    name: 'Arakawa River, Kita Ward', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221281003.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-arakawa-2', lat: 35.7500, lng: 139.7855,
    name: 'Arakawa River, Adachi Ward', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221281004.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-tamagawa-1', lat: 35.5950, lng: 139.6500,
    name: 'Tama River, Ota Ward', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221320001.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-tamagawa-2', lat: 35.6020, lng: 139.6350,
    name: 'Tama River, Setagaya Ward', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221320002.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-tamagawa-4', lat: 35.6200, lng: 139.6100,
    name: 'Tama River, Komae', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221320004.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-tamagawa-5', lat: 35.6350, lng: 139.5900,
    name: 'Tama River, Chofu', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221320005.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-tamagawa-6', lat: 35.6450, lng: 139.5650,
    name: 'Tama River, Fuchu', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221320006.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-sumida-1', lat: 35.7200, lng: 139.8000,
    name: 'Sumida River, Asakusa', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221281010.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-sumida-2', lat: 35.6900, lng: 139.7950,
    name: 'Sumida River, Ryogoku', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221281011.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-sumida-3', lat: 35.6600, lng: 139.7850,
    name: 'Sumida River, Tsukiji', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221281012.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-nakagawa-1', lat: 35.7600, lng: 139.8500,
    name: 'Naka River, Katsushika Ward', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/221281020.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-tsurumi-1', lat: 35.5100, lng: 139.6700,
    name: 'Tsurumi River, Yokohama', city: 'Yokohama', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/303585001.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-tsurumi-2', lat: 35.5250, lng: 139.6200,
    name: 'Tsurumi River, Midori Ward', city: 'Yokohama', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/303585002.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-meguro-1', lat: 35.6400, lng: 139.7100,
    name: 'Meguro River, Meguro Ward', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/303329001.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-meguro-2', lat: 35.6320, lng: 139.7200,
    name: 'Meguro River, Shinagawa Ward', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/303329002.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-kanda-1', lat: 35.7000, lng: 139.7600,
    name: 'Kanda River, Chiyoda', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/303329005.jpg', source: 'MLIT river.go.jp',
  },
  {
    id: 'jp-river-shakujii-1', lat: 35.7400, lng: 139.6700,
    name: 'Shakujii River, Nerima', city: 'Tokyo', country: 'Japan',
    feed_url: 'https://cam.river.go.jp/cam/now/303329010.jpg', source: 'MLIT river.go.jp',
  },
];

export async function fetchJapanCameras(): Promise<CctvCamera[]> {
  return JAPAN_CAMERAS;
}
