import { google } from '@ai-sdk/google';
import { streamText, tool } from 'ai';
import { z } from 'zod';

// Allow streaming responses up to 30 seconds
export const maxDuration = 30;

const marketMapSchema = z.object({
  niche_name: z.string().describe('The name of the market niche (e.g., "Solid State Batteries")'),
  data_sources: z.array(z.object({
    type: z.enum(['rss', 'api', 'webhook', 'custom']).describe('The type of data source'),
    url: z.string().describe('The URL or endpoint for the data source'),
    name: z.string().describe('A human-readable name for the source')
  })).describe('The list of data sources to ingest from'),
  ontology: z.object({
    entities: z.array(z.string()).describe('The types of entities to extract (e.g., ["Company", "Technology", "Researcher"])'),
    relationships: z.array(z.object({
      source: z.string().describe('The source entity type'),
      type: z.string().describe('The relationship type (e.g., "DEVELOPS", "RESEARCHES")'),
      target: z.string().describe('The target entity type')
    })).describe('The relationships between entities')
  }).describe('The graph ontology schema for entity extraction')
});

export async function POST(req: Request) {
  const { messages } = await req.json();

  const result = await streamText({
    model: google('gemini-3.1-pro-preview'),
    system: `You are an expert VC/PE Market Intelligence Consultant. 
Your goal is to help the user map a specific market ecosystem (e.g., "Solid State Batteries", "AI Agents in Healthcare").
Ask questions to understand their niche, what kind of data sources they care about (RSS feeds, specific websites, etc.), and what entities/relationships they want to extract.

Once you have enough information to define the niche, the data sources, and the graph ontology (entities and relationships), call the \`finalize_market_map\` tool to generate the configuration payload. Do not call this tool until you are confident you have a good understanding of the user's needs.`,
    messages,
    tools: {
      finalize_market_map: tool({
        description: 'Generate the final JSON configuration for the market mapping ingestion pipeline.',
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        parameters: marketMapSchema as any
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } as any)
    }
  });

  return result.toTextStreamResponse();
}
