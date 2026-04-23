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
      systemPrompt = `You are an expert VC/PE Market Intelligence Consultant. Your goal is to define the user's target market AND their investment lens.

CRITICAL INSTRUCTIONS:
1. DO NOT ask the user to narrow down their topic. If they suggest a broad industry (like "Electric Power" or "SpaceTech"), accept the broad scope immediately.
2. INSTEAD of narrowing the topic, proactively help them refine their *investment lens* and *disruptor focus*. Ask 1 or 2 quick questions to understand their angle:
   - Are they looking at this from a Venture Capital (early-stage disruptors, startups) or Private Equity (mature companies, M&A, consolidation) perspective?
   - Are there any specific macro trends, adjacent technologies, or known disruptors they are particularly interested in tracking within this space?
3. Wait for the user to respond to your clarifying questions.
4. Once you understand their broad niche AND their investment lens, combine them into a single, highly descriptive niche string (e.g., "Electric Power with a focus on early-stage AI/Data Center disruptors").
5. Call the \`lock_in_niche\` tool with this descriptive string to advance to the next step.`;
      
      tools = {
        lock_in_niche: tool({
          description: 'Lock in the market niche and advance to defining entities.',
          parameters: z.object({
            niche_name: z.string().describe('The name of the market niche (e.g., "Solid State Batteries")'),
            message_to_user: z.string().describe('A conversational message to the user explaining what you did and asking for the next input.'),
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
CRITICAL INSTRUCTIONS:
1. You MUST write your conversational text response inside the \`message_to_user\` parameter of the tool call. Explain what you are adding and ask for the user's feedback.
2. Call the \`sync_entities\` tool to reflect the current list of entities when you are proposing them.
3. ONLY call the \`finalize_entities\` tool AFTER the user explicitly replies with "looks good", "yes", or "move on" to your proposed list.`;
      
      tools = {
        sync_entities: tool({
          description: 'Sync the complete list of entities and propose them to the user.',
          parameters: z.object({
            entities: z.array(z.string()).describe('The complete, current list of entities (e.g., ["Company", "Founder"])'),
            message_to_user: z.string().describe('A conversational message to the user explaining what you added and asking for their feedback.'),
          }),
          execute: async ({ entities }) => {
            return { success: true, message: `Synced ${entities.length} entities.` };
          }
        }),
        finalize_entities: tool({
          description: 'Lock in the entities and advance to defining relationships. Call this ONLY when the user explicitly agrees.',
          parameters: z.object({
            message_to_user: z.string().describe('A conversational message acknowledging the user\'s agreement and transitioning to relationships.'),
          }),
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

Your job is to proactively help the user define relationships.
CRITICAL INSTRUCTIONS:
1. You MUST write your conversational text response inside the \`message_to_user\` parameter of the tool call. Explain what you are adding and ask for the user's feedback.
2. Call the \`sync_relationships\` tool to reflect the current list of relationships when you are proposing them.
3. ONLY call the \`finalize_relationships\` tool AFTER the user explicitly replies with "looks good", "yes", or "move on" to your proposed list.`;
      
      tools = {
        sync_relationships: tool({
          description: 'Sync the complete list of relationships and entities, and propose them to the user.',
          parameters: z.object({
            relationships: z.array(z.object({
              source: z.string().describe('The source entity type'),
              type: z.string().describe('The relationship type (e.g., "DEVELOPS")'),
              target: z.string().describe('The target entity type')
            })).describe('The complete, current list of relationships'),
            entities: z.array(z.string()).describe('The complete, current list of entities. Add to this list if a new relationship requires a new entity.'),
            message_to_user: z.string().describe('A conversational message to the user explaining what you added and asking for their feedback.'),
          }),
          execute: async ({ relationships, entities }) => {
            return { success: true, message: `Synced ${relationships.length} relationships and ${entities.length} entities.` };
          }
        }),
        finalize_relationships: tool({
          description: 'Lock in the relationships and advance to gathering data sources. Call this ONLY when the user explicitly agrees.',
          parameters: z.object({
            message_to_user: z.string().describe('A conversational message acknowledging the user\'s agreement and transitioning to data sources.'),
          }),
          execute: async () => {
            return { success: true, message: `Relationships finalized. The system will now advance to data sources.` };
          }
        })
      };
      break;

  }

  const result = await streamText({
    model: google('gemini-3-flash-preview'),
    system: systemPrompt,
    messages,
    tools,
  });

  return result.toDataStreamResponse();
}
