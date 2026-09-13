const https = require('https');
const fs = require('fs');

function fetchHTML(url) {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => resolve(data));
      res.on('error', reject);
    }).on('error', reject);
  });
}

async function scrapeGermany() {
  const html = await fetchHTML('https://www.skylinewebcams.com/en/webcam/deutschland.html');
  const regionRE = /href="(\/en\/webcam\/deutschland\/[^"]+\.html)"/g;
  const regions = new Set();
  let m;
  while ((m = regionRE.exec(html)) !== null) {
    if (!m[1].includes('index.html')) regions.add('https://www.skylinewebcams.com' + m[1]);
  }
  
  const cams = [];
  for (const url of [...regions].slice(0, 5)) {
    const rh = await fetchHTML(url);
    const camRE = /href="(\/en\/webcam\/deutschland\/[^"]+\.html)"[^>]*>.*?<img[^>]*src="(https:\/\/cdn\d*\.skylinewebcams\.com\/[^"]+)"[^>]*>.*?<div class="title">([^<]+)<\/div>/gs;
    while ((m = camRE.exec(rh)) !== null) {
      if (!cams.find(c => c.external_url === 'https://www.skylinewebcams.com' + m[1])) {
        cams.push({
          external_url: 'https://www.skylinewebcams.com' + m[1],
          feed_url: '/api/cctv/proxy?url=' + encodeURIComponent(m[2]),
          name: m[3].trim().replace(/&amp;/g, '&').replace(/&#039;/g, "'")
        });
      }
    }
  }
  console.log(JSON.stringify(cams, null, 2));
}

scrapeGermany().catch(console.error);
