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
      systemPrompt = `You are an expert VC Market Intelligence Consultant. Your goal is to define the user's niche. If the user is vague (e.g., 'spacetech broadly'), you MUST ask pointed, multiple-choice style questions to narrow them down (e.g., 'Are we focusing on Launch Vehicles, Satellites, or Earth Observation?'). Gently reframe their answers until you have a concrete, specific niche. Once you do, call the \`lock_in_niche\` tool to advance to the next step.`;
      
      tools = {
        lock_in_niche: tool({
          description: 'Lock in the market niche and advance to defining entities.',
          parameters: z.object({
            niche_name: z.string().describe('The name of the market niche (e.g., "Solid State Batteries")'),
          }),
          execute: async ({ niche_name }) => {
            return { success: true, message: `Niche locked as "${niche_name}". The system will now advance to defining entities.` };
          }
        })
      };
      break;

    case 'entities':
      systemPrompt = `You are an expert VC/PE Market Intelligence Consultant. 
The user has chosen the niche: "${currentConfig.niche}".
We are currently defining the Entities for the Graph Ontology.
CURRENT ENTITIES: ${JSON.stringify(currentConfig.schema?.entities || [])}
You can help them by adding or removing entities.
If they ask to add an entity, call \`add_entity\`. If they ask to remove one, call \`remove_entity\`.
IMPORTANT: Focus ONLY on entities right now. Do not discuss relationships or data sources.
Once you have proposed a complete initial draft of the entities and the user agrees they look good, you MUST immediately call the \`finalize_entities\` tool to advance to the next step.`;
      
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
        finalize_entities: tool({
          description: 'Finalize the entities schema and advance to defining relationships.',
          parameters: z.object({}),
          execute: async () => {
            return { success: true, message: `Entities finalized. The system will now advance to defining relationships.` };
          }
        })
      };
      break;

    case 'relationships':
      systemPrompt = `You are an expert VC/PE Market Intelligence Consultant. 
The user has chosen the niche: "${currentConfig.niche}".
We have defined these entities: ${JSON.stringify(currentConfig.schema?.entities || [])}
We are currently defining the Relationships between these entities.
CURRENT RELATIONSHIPS: ${JSON.stringify(currentConfig.schema?.relationships || [])}
You can help them by adding relationships. Call \`add_relationship\`.
IMPORTANT: Focus ONLY on relationships right now. Do not discuss data sources.
Once you have proposed a complete initial draft of the relationships and the user agrees they look good, you MUST immediately call the \`finalize_relationships\` tool to advance to the next step.`;
      
      tools = {
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
        }),
        finalize_relationships: tool({
          description: 'Finalize the relationships schema and advance to gathering data sources.',
          parameters: z.object({}),
          execute: async () => {
            return { success: true, message: `Relationships finalized. The system will now advance to gathering data sources.` };
          }
        })
      };
      break;

    case 'sources':
      systemPrompt = `You are an expert VC/PE Market Intelligence Consultant. 
The user has chosen the niche: "${currentConfig.niche}".
We are now gathering data sources (RSS feeds, APIs, websites) to ingest data from.
Suggest relevant sources for this niche. If the user agrees or provides a URL, call \`add_source\`.
If they want to remove a source, call \`remove_source\`.
Once you have gathered sufficient data sources and the user is ready to proceed, you MUST immediately call the \`finalize_sources\` tool to advance to the final review step.`;
      
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
        }),
        finalize_sources: tool({
          description: 'Finalize the data sources and advance to the review step.',
          parameters: z.object({}),
          execute: async () => {
            return { success: true, message: `Data sources finalized. The system will now advance to the review step.` };
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
