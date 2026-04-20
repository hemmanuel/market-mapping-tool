const { createGoogleGenerativeAI } = require('@ai-sdk/google');
const { generateText } = require('ai');

const google = createGoogleGenerativeAI({ apiKey: 'test' });
const model = google('gemini-3.1-pro-preview');

console.log('Model loaded successfully:', !!model);
