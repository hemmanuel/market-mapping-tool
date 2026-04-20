import { streamText } from 'ai';
import { createGoogleGenerativeAI } from '@ai-sdk/google';

// Allow streaming responses up to 30 seconds
export const maxDuration = 30;

const google = createGoogleGenerativeAI({
  apiKey: process.env.GEMINI_API_KEY || '',
});

export async function POST(req: Request) {
  const { messages } = await req.json();

  const systemPrompt = `You are an expert VC/PE Data Strategist. 
The user has just finished defining their market map schema and has entered the Data Command Center.
The backend engine is currently building the "backbone" of their knowledge graph by doing an initial deep dive.

Your job is to proactively guide the user to determine the "heartbeat" data sources for daily updates.

CRITICAL INSTRUCTIONS:
1. When the user sends "SYSTEM_AUTO_PROMPT: INTRODUCE_DATA_STRATEGY", you MUST proactively introduce yourself and the current phase.
   - Example: "We are now determining the data sources which will power your heartbeat data feed. While the engine builds the backbone of your knowledge graph in the background, let's figure out where we should pull daily updates from..."
2. Ask the user what kind of sources they want to monitor (e.g., specific news sites, regulatory filings, company blogs, SEC databases).
3. Keep your tone professional, consultative, and concise.
4. Do NOT mention the SYSTEM_AUTO_PROMPT string in your response.`;

  const result = await streamText({
    model: google('gemini-3-flash-preview'),
    system: systemPrompt,
    messages,
  });

  return result.toDataStreamResponse();
}
