const https = require('https');
const fs = require('fs');

https.get('https://www.skylinewebcams.com/en/webcam/italia.html', (res) => {
  let data = '';
  res.on('data', c => data += c);
  res.on('end', () => {
    const matches = [...data.matchAll(/href="(\/en\/webcam\/italia\/[^"]+)"[\s\S]*?src="(https:\/\/cdn[^"]+live\d+\.jpg)"[\s\S]*?<div class="title">([^<]+)<\/div>/g)];
    console.log('Found:', matches.length);
    if(matches.length > 0) {
      const cams = matches.map(m => ({
        url: 'https://www.skylinewebcams.com' + m[1],
        img: m[2],
        title: m[3].trim()
      }));
      fs.writeFileSync('italy_skyline.json', JSON.stringify(cams, null, 2));
      console.log('Saved to italy_skyline.json');
    }
  });
}).on('error', console.error);
