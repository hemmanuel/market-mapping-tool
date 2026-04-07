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
      systemPrompt = `You are an expert VC Market Intelligence Consultant. Your goal is to define the user's niche. 
      You may initially suggest narrowing down a broad topic (e.g., 'spacetech') to make it more actionable. 
      HOWEVER, if the user insists on keeping it broad (e.g., "map the whole industry" or "the customer is always right"), you MUST accept their decision immediately without arguing. 
      Once a niche (broad or narrow) is agreed upon, call the \`lock_in_niche\` tool to advance to the next step.`;
      
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

Your job is to proactively help the user define entities.
Always respond to the user with a conversational text message.
In the same turn, ALWAYS call the \`sync_entities_state\` tool to reflect the complete, current list of entities.
If you are still brainstorming or adding entities, set \`is_finished: false\`.
ONLY when the user explicitly agrees the list is complete (e.g., "looks good", "we are done", "move on"), set \`is_finished: true\`.`;
      
      tools = {
        sync_entities_state: tool({
          description: 'Sync the complete list of entities and indicate if the user is finished.',
          parameters: z.object({
            entities: z.array(z.string()).describe('The complete, current list of entities (e.g., ["Company", "Founder"])'),
            is_finished: z.boolean().describe('True ONLY if the user explicitly agreed the list is complete and wants to move on.')
          }),
          execute: async ({ entities, is_finished }) => {
            return { success: true, message: `Synced ${entities.length} entities. Finished: ${is_finished}` };
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

Your job is to proactively help the user define relationships.
Always respond to the user with a conversational text message.
In the same turn, ALWAYS call the \`sync_relationships_state\` tool to reflect the complete, current list of relationships.
If you are still brainstorming or adding relationships, set \`is_finished: false\`.
ONLY when the user explicitly agrees the list is complete (e.g., "looks good", "we are done", "move on"), set \`is_finished: true\`.`;
      
      tools = {
        sync_relationships_state: tool({
          description: 'Sync the complete list of relationships and indicate if the user is finished.',
          parameters: z.object({
            relationships: z.array(z.object({
              source: z.string().describe('The source entity type'),
              type: z.string().describe('The relationship type (e.g., "DEVELOPS")'),
              target: z.string().describe('The target entity type')
            })).describe('The complete, current list of relationships'),
            is_finished: z.boolean().describe('True ONLY if the user explicitly agreed the list is complete and wants to move on.')
          }),
          execute: async ({ relationships, is_finished }) => {
            return { success: true, message: `Synced ${relationships.length} relationships. Finished: ${is_finished}` };
          }
        })
      };
      break;

    case 'sources':
      systemPrompt = `You are an expert VC/PE Market Intelligence Consultant. 
The user has chosen the niche: "${currentConfig.niche}".
We are now gathering data sources (RSS feeds, APIs, websites) to ingest data from.

Your job is to proactively help the user define data sources.
Always respond to the user with a conversational text message.
In the same turn, ALWAYS call the \`sync_sources_state\` tool to reflect the complete, current list of data sources.
If you are still brainstorming or adding sources, set \`is_finished: false\`.
ONLY when the user explicitly agrees the list is complete (e.g., "looks good", "we are done", "move on"), set \`is_finished: true\`.`;
      
      tools = {
        sync_sources_state: tool({
          description: 'Sync the complete list of data sources and indicate if the user is finished.',
          parameters: z.object({
            sources: z.array(z.object({
              type: z.enum(['rss', 'api', 'webhook', 'custom']).describe('The type of data source'),
              url: z.string().describe('The URL or endpoint for the data source'),
              name: z.string().describe('A human-readable name for the source')
            })).describe('The complete, current list of sources'),
            is_finished: z.boolean().describe('True ONLY if the user explicitly agreed the list is complete and wants to move on.')
          }),
          execute: async ({ sources, is_finished }) => {
            return { success: true, message: `Synced ${sources.length} sources. Finished: ${is_finished}` };
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
    maxSteps: 5, // Allow the model to call tools and respond with text in the same turn
  });

  return result.toDataStreamResponse();
}
