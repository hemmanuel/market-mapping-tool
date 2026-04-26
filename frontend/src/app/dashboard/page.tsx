"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, Plus, Database, Calendar } from "lucide-react";

interface Pipeline {
  id: string;
  name: string;
  created_at: string;
  document_count: number;
}

export default function DashboardPage() {
  const { getToken, isLoaded, userId } = useAuth();
  const router = useRouter();
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoaded) return;
    if (!userId) {
      router.push("/sign-in");
      return;
    }

    const fetchPipelines = async () => {
      try {
        const token = await getToken();
        const response = await fetch("http://localhost:8000/api/v1/pipelines", {
          headers: {
            "Authorization": `Bearer ${token}`,
          },
        });

        if (!response.ok) {
          throw new Error("Failed to fetch pipelines");
        }

        const data = await response.json();
        setPipelines(data);
      } catch (err: any) {
        console.error("Error fetching pipelines:", err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchPipelines();
  }, [isLoaded, userId, getToken, router]);

  if (loading || !isLoaded) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-slate-50">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 p-8">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Your Market Maps</h1>
            <p className="text-slate-500 mt-2">Manage your data pipelines and knowledge graphs.</p>
          </div>
          <Button onClick={() => router.push("/new")} className="bg-blue-600 hover:bg-blue-700 text-white">
            <Plus className="w-4 h-4 mr-2" />
            Create New Map
          </Button>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-md mb-8">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <Card 
            className="bg-white border-slate-200 hover:border-blue-500/50 cursor-pointer transition-colors flex flex-col items-center justify-center min-h-[200px] border-dashed shadow-sm"
            onClick={() => router.push("/new")}
          >
            <CardContent className="flex flex-col items-center justify-center text-center pt-6">
              <div className="w-12 h-12 rounded-full bg-blue-50 flex items-center justify-center mb-4">
                <Plus className="w-6 h-6 text-blue-600" />
              </div>
              <h3 className="text-lg font-medium text-slate-900">Create New Map</h3>
              <p className="text-sm text-slate-500 mt-2">Start a new market mapping workflow</p>
            </CardContent>
          </Card>

          {pipelines.map((pipeline) => (
            <Card 
              key={pipeline.id} 
              className="bg-white border-slate-200 hover:border-slate-300 cursor-pointer transition-colors flex flex-col shadow-sm"
              onClick={() => router.push(`/pipeline/${pipeline.id}/data`)}
            >
              <CardHeader>
                <CardTitle className="text-xl text-slate-900 truncate">{pipeline.name}</CardTitle>
                <CardDescription className="text-slate-500">Market Map Pipeline</CardDescription>
              </CardHeader>
              <CardContent className="flex-grow">
                <div className="flex items-center text-sm text-slate-600 mb-2">
                  <Database className="w-4 h-4 mr-2 text-blue-600" />
                  {pipeline.document_count} chunks ingested
                </div>
                <div className="flex items-center text-sm text-slate-600">
                  <Calendar className="w-4 h-4 mr-2 text-emerald-600" />
                  Created {new Date(pipeline.created_at).toLocaleDateString()}
                </div>
              </CardContent>
              <CardFooter>
                <Button variant="secondary" className="w-full bg-slate-100 hover:bg-slate-200 text-slate-900">
                  View Command Center
                </Button>
              </CardFooter>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}