import { Check } from "lucide-react";
import { OnboardingStep } from "@/lib/types";

const STEPS = [
  { id: 'niche', label: 'Identify Niche' },
  { id: 'entities', label: 'Entities Schema' },
  { id: 'relationships', label: 'Relationships Schema' },
  { id: 'sources', label: 'Data Sources' },
  { id: 'review', label: 'Review' },
];

interface TimelineProps {
  currentStep: OnboardingStep;
}

export function Timeline({ currentStep }: TimelineProps) {
  const currentIndex = STEPS.findIndex(s => s.id === currentStep);

  return (
    <div className="w-full py-4 px-8 border-b border-slate-200 bg-white">
      <div className="max-w-3xl mx-auto flex items-center justify-between relative">
        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-full h-0.5 bg-slate-200 -z-10"></div>
        <div 
          className="absolute left-0 top-1/2 -translate-y-1/2 h-0.5 bg-blue-600 transition-all duration-500 -z-10"
          style={{ width: `${(currentIndex / (STEPS.length - 1)) * 100}%` }}
        ></div>
        
        {STEPS.map((step, index) => {
          const isCompleted = index < currentIndex;
          const isCurrent = index === currentIndex;
          
          return (
            <div key={step.id} className="flex flex-col items-center gap-2 bg-white px-2">
              <div 
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors duration-300
                  ${isCompleted ? 'bg-blue-600 text-white' : 
                    isCurrent ? 'bg-blue-100 text-blue-700 border-2 border-blue-600' : 
                    'bg-slate-100 text-slate-400 border border-slate-200'}`}
              >
                {isCompleted ? <Check className="w-4 h-4" /> : index + 1}
              </div>
              <span className={`text-xs font-medium ${isCurrent ? 'text-blue-700' : isCompleted ? 'text-slate-700' : 'text-slate-400'}`}>
                {step.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
