const https = require('https');

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

async function scrapeItaly() {
  console.log('Fetching Italy index...');
  const html = await fetchHTML('https://www.skylinewebcams.com/en/webcam/italia.html');
  
  // Find all category/region links
  const regionRE = /href="(\/en\/webcam\/italia\/[^"]+\.html)"/g;
  const regions = new Set();
  let m;
  while ((m = regionRE.exec(html)) !== null) {
    if (!m[1].includes('index.html')) {
      regions.add('https://www.skylinewebcams.com' + m[1]);
    }
  }
  
  console.log(`Found ${regions.size} regions. Fetching top 3 regions...`);
  const topRegions = [...regions].slice(0, 3); // Just grab 3 regions to avoid too many requests
  
  const cams = [];
  for (const url of topRegions) {
    console.log('Fetching', url);
    const rh = await fetchHTML(url);
    const camRE = /href="(\/en\/webcam\/italia\/[^"]+\.html)"[^>]*>.*?<img[^>]*src="(https:\/\/cdn\d*\.skylinewebcams\.com\/[^"]+)"[^>]*>.*?<div class="title">([^<]+)<\/div>/gs;
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
  
  console.log(`Found ${cams.length} cameras!`);
  cams.slice(0, 5).forEach(c => console.log(c));
}

scrapeItaly().catch(console.error);
