const express = require('express');
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const fs = require('fs');
const path = require('path');

const app = express();
// Increase body size limit for base64 image transfers
app.use(express.json({ limit: '10mb' }));

const PORT = 3000;

// Resolve local Chrome path dynamically on Windows
const userProfile = process.env.USERPROFILE || 'C:\\Users\\prave';
const chromePath = path.join(userProfile, 'AppData', 'Local', 'Google', 'Chrome', 'Application', 'chrome.exe');
const executablePath = fs.existsSync(chromePath) ? chromePath : undefined;

if (executablePath) {
    console.log(`[WHATSAPP BOT] Using local Chrome executable: ${chromePath}`);
} else {
    console.log('[WHATSAPP BOT] Local Chrome executable not found, using default Puppeteer browser.');
}

// Initialize WhatsApp client with LocalAuth so session is saved
const client = new Client({
    authStrategy: new LocalAuth({
        dataPath: './session'
    }),
    authTimeoutMs: 90000,
    qrTimeoutMs: 90000,
    puppeteer: {
        headless: true,
        executablePath: executablePath,
        protocolTimeout: 90000,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--no-first-run',
            '--no-zygote'
        ]
    }
});

// Generate QR Code for WhatsApp Web linking
client.on('qr', (qr) => {
    console.log('\n==================================================================');
    console.log('SCAN THIS QR CODE WITH YOUR WHATSAPP MOBILE APP (LINK A DEVICE):');
    console.log('==================================================================\n');
    qrcode.generate(qr, { small: true });
});

client.on('ready', () => {
    console.log('\n[WHATSAPP BOT] Client is ready and logged in!');
});

client.on('auth_failure', msg => {
    console.error('[WHATSAPP BOT] Authentication failure:', msg);
});

client.on('disconnected', (reason) => {
    console.log('[WHATSAPP BOT] Client was logged out. Reason:', reason);
});

// POST endpoint to send alerts
app.post('/send', async (req, res) => {
    const { to, message, image } = req.body;

    if (!to || !message) {
        return res.status(400).json({ error: 'Missing "to" or "message" in request body.' });
    }

    try {
        // Clean phone number (remove +, spaces, and format for WhatsApp)
        let formattedNum = to.replace(/[^0-9]/g, '');
        if (!formattedNum.endsWith('@c.us')) {
            formattedNum = `${formattedNum}@c.us`;
        }

        if (image) {
            console.log(`[WHATSAPP BOT] Sending media message to: ${formattedNum}`);
            // Strip base64 schema prefix if present (e.g. data:image/jpeg;base64,)
            let base64Data = image;
            if (image.includes(',')) {
                base64Data = image.split(',')[1];
            }
            const media = new MessageMedia('image/jpeg', base64Data, 'screenshot.jpg');
            await client.sendMessage(formattedNum, media, { caption: message });
        } else {
            console.log(`[WHATSAPP BOT] Sending text message to: ${formattedNum}`);
            await client.sendMessage(formattedNum, message);
        }

        res.status(200).json({ success: true, message: 'Message sent successfully.' });
    } catch (err) {
        console.error('[WHATSAPP BOT] Error sending message:', err);
        res.status(500).json({ error: err.message });
    }
});

app.get('/status', (req, res) => {
    res.json({ ready: client.info ? true : false });
});

// Initialize client
console.log('[WHATSAPP BOT] Starting WhatsApp client...');
client.initialize();

// Start HTTP Server
app.listen(PORT, () => {
    console.log(`[WHATSAPP BOT] API listening on http://localhost:${PORT}`);
});
