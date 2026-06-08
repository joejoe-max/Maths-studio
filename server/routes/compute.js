import express from 'express';
import fetch from 'node-fetch';

const router = express.Router();
const FASTAPI_BASE_URL = process.env.FASTAPI_BASE_URL || 'http://127.0.0.1:9999';

function writeSseError(res, message) {
    res.write(`data: ${JSON.stringify({ type: 'error', message })}\n\n`);
    res.end();
}

async function proxySse(req, res, fastapiPath) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    try {
        const response = await fetch(`${FASTAPI_BASE_URL}${fastapiPath}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
            body: JSON.stringify(req.body),
        });

        if (!response.ok) {
            const errBody = await response.text();
            console.error(`[Proxy] Backend Error (${response.status}):`, errBody);
            try {
                const jsonErr = JSON.parse(errBody);
                throw new Error(jsonErr.error || jsonErr.message || `Backend responded with ${response.status}`);
            } catch {
                if (response.status === 404) throw new Error('Solver endpoint not found.');
                if (response.status === 502 || response.status === 503) throw new Error('Solver engine is currently starting or unavailable.');
                throw new Error(`Backend responded with ${response.status}: ${errBody.substring(0, 120)}`);
            }
        }

        for await (const chunk of response.body) {
            res.write(chunk);
        }
        res.end();
    } catch (error) {
        console.error('Proxy Error:', error);
        writeSseError(res, error.message || 'Backend proxy error.');
    }
}

async function proxyJson(req, res, fastapiPath) {
    try {
        const response = await fetch(`${FASTAPI_BASE_URL}${fastapiPath}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(req.body),
        });
        const text = await response.text();
        res.status(response.status);
        res.type(response.headers.get('content-type') || 'application/json');
        res.send(text);
    } catch (error) {
        console.error('Proxy Error:', error);
        res.status(502).json({ type: 'error', message: error.message || 'Backend proxy error.' });
    }
}

router.post('/', async (req, res) => proxySse(req, res, '/api/compute/solve'));
router.post('/solve', async (req, res) => proxySse(req, res, '/api/compute/solve'));
router.post('/analyze', async (req, res) => proxyJson(req, res, '/api/compute/analyze'));

export default router;
