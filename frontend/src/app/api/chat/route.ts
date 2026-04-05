import { createGoogleGenerativeAI } from '@ai-sdk/google';
import { streamText, tool, CoreMessage } from 'ai';
import { z } from 'zod';
import { OnboardingStep, PipelineConfig } from '@/lib/types';

// Allow streaming responses up to 30 seconds
export const maxDuration = 30;

const google = createGoogleGenerativeAI({
  apiKey: process.env.GEMINI_API_KEY || '',
});

export async function POST(req: Request) {
  const { messages, currentStep, currentConfig } = await req.json() as { 
    messages: CoreMessage[], 
    currentStep: OnboardingStep, 
    currentConfig: PipelineConfig 
  };

  let systemPrompt = '';
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let tools: Record<string, any> = {};

  switch (currentStep) {
    case 'niche':
      systemPrompt = `You are an expert VC/PE Market Intelligence Consultant. 
Your goal right now is ONLY to understand the specific market ecosystem (niche) the user wants to map (e.g., "Solid State Batteries", "AI Agents in Healthcare").
Ask clarifying questions if needed. Do NOT ask about data sources or schemas yet.
Once you clearly understand the niche, call the \`lock_in_niche\` tool to save it and advance to the next step.`;
      
      tools = {
        lock_in_niche: tool({
          description: 'Lock in the market niche and advance to schema generation.',
          parameters: z.object({
            niche_name: z.string().describe('The name of the market niche (e.g., "Solid State Batteries")'),
          }),
          execute: async ({ niche_name }) => {
            return { success: true, message: `Niche locked as "${niche_name}". The system will now generate a draft schema.` };
          }
        })
      };
      break;

    case 'schema':
      systemPrompt = `You are an expert VC/PE Market Intelligence Consultant. 
The user has chosen the niche: "${currentConfig.niche}".
We are currently defining the Graph Ontology (Entities and Relationships) for this niche.
The user is viewing an interactive form of the schema.
You can help them by adding entities, removing entities, or adding relationships based on their requests.
If they ask to add an entity, call \`add_entity\`. If they ask to remove one, call \`remove_entity\`. If they ask to add a relationship, call \`add_relationship\`.
Do not discuss data sources yet.`;
      
      tools = {
        add_entity: tool({
          description: 'Add a new entity type to the schema.',
          parameters: z.object({
            entity_name: z.string().describe('The name of the entity to add (e.g., "Company", "Patent")'),
          }),
          execute: async ({ entity_name }) => {
            return { success: true, message: `Added entity "${entity_name}".` };
          }
        }),
        remove_entity: tool({
          description: 'Remove an entity type from the schema.',
          parameters: z.object({
            entity_name: z.string().describe('The name of the entity to remove'),
          }),
          execute: async ({ entity_name }) => {
            return { success: true, message: `Removed entity "${entity_name}".` };
          }
        }),
        add_relationship: tool({
          description: 'Add a new relationship between two entities.',
          parameters: z.object({
            source: z.string().describe('The source entity type'),
            type: z.string().describe('The relationship type (e.g., "DEVELOPS")'),
            target: z.string().describe('The target entity type')
          }),
          execute: async ({ source, type, target }) => {
            return { success: true, message: `Added relationship: ${source} -[${type}]-> ${target}.` };
          }
        })
      };
      break;

    case 'sources':
      systemPrompt = `You are an expert VC/PE Market Intelligence Consultant. 
The user has chosen the niche: "${currentConfig.niche}".
We are now gathering data sources (RSS feeds, APIs, websites) to ingest data from.
Suggest relevant sources for this niche. If the user agrees or provides a URL, call \`add_source\`.
If they want to remove a source, call \`remove_source\`.`;
      
      tools = {
        add_source: tool({
          description: 'Add a new data source to the pipeline.',
          parameters: z.object({
            type: z.enum(['rss', 'api', 'webhook', 'custom']).describe('The type of data source'),
            url: z.string().describe('The URL or endpoint for the data source'),
            name: z.string().describe('A human-readable name for the source')
          }),
          execute: async ({ type, url, name }) => {
            return { success: true, message: `Added ${type} source "${name}" (${url}).` };
          }
        }),
        remove_source: tool({
          description: 'Remove a data source from the pipeline.',
          parameters: z.object({
            url: z.string().describe('The URL of the source to remove'),
          }),
          execute: async ({ url }) => {
            return { success: true, message: `Removed source with URL "${url}".` };
          }
        })
      };
      break;
      
    case 'review':
      systemPrompt = `You are an expert VC/PE Market Intelligence Consultant. 
The configuration is complete. The user is reviewing the final pipeline configuration.
Answer any final questions they have before they deploy.`;
      break;
  }

  const result = await streamText({
    model: google('gemini-3.1-pro-preview'),
    system: systemPrompt,
    messages,
    tools,
  });

  return result.toDataStreamResponse();
}
