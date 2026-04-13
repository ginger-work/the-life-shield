/**
 * The Life Shield Portal - Main Client Dashboard
 * 7 Tabs: Home, Credit Repair, Agent, Sessions, Store, Vault, Budget
 */

import React, { useState, useEffect } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Home,
  FileText,
  MessageSquare,
  Calendar,
  Store,
  Lock,
  DollarSign,
} from 'lucide-react';

// Tab Components
import HomeTab from '@/components/portal/HomeTab';
import CreditRepairTab from '@/components/portal/CreditRepairTab';
import AgentTab from '@/components/portal/AgentTab';
import SessionsTab from '@/components/portal/SessionsTab';
import StoreTab from '@/components/portal/StoreTab';
import VaultTab from '@/components/portal/VaultTab';
import BudgetTab from '@/components/portal/BudgetTab';

export default function Portal() {
  const [activeTab, setActiveTab] = useState('home');
  const [clientData, setClientData] = useState(null);
  const [loading, setLoading] = useState(true);

  // Load client data
  useEffect(() => {
    const fetchClientData = async () => {
      try {
        const response = await fetch('/api/portal/client', {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('accessToken')}`
          }
        });
        const data = await response.json();
        setClientData(data);
      } catch (error) {
        console.error('Error loading client data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchClientData();
  }, []);

  if (loading) {
    return <div className="flex items-center justify-center h-screen">Loading...</div>;
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <div className="bg-gradient-to-r from-navy-900 to-charcoal-800 text-white p-6">
        <div className="max-w-7xl mx-auto">
          <h1 className="text-3xl font-bold">The Life Shield</h1>
          <p className="text-muted mt-2">Your Personal Credit Success Team</p>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto p-6">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          {/* Tab Navigation */}
          <TabsList className="grid w-full grid-cols-7 mb-6">
            <TabsTrigger value="home" className="flex items-center gap-2">
              <Home size={18} />
              <span className="hidden sm:inline">Home</span>
            </TabsTrigger>
            <TabsTrigger value="credit" className="flex items-center gap-2">
              <FileText size={18} />
              <span className="hidden sm:inline">Credit</span>
            </TabsTrigger>
            <TabsTrigger value="agent" className="flex items-center gap-2">
              <MessageSquare size={18} />
              <span className="hidden sm:inline">Agent</span>
            </TabsTrigger>
            <TabsTrigger value="sessions" className="flex items-center gap-2">
              <Calendar size={18} />
              <span className="hidden sm:inline">Sessions</span>
            </TabsTrigger>
            <TabsTrigger value="store" className="flex items-center gap-2">
              <Store size={18} />
              <span className="hidden sm:inline">Store</span>
            </TabsTrigger>
            <TabsTrigger value="vault" className="flex items-center gap-2">
              <Lock size={18} />
              <span className="hidden sm:inline">Vault</span>
            </TabsTrigger>
            <TabsTrigger value="budget" className="flex items-center gap-2">
              <DollarSign size={18} />
              <span className="hidden sm:inline">Budget</span>
            </TabsTrigger>
          </TabsList>

          {/* Tab Content */}
          <TabsContent value="home" className="mt-0">
            <HomeTab clientData={clientData} />
          </TabsContent>

          <TabsContent value="credit" className="mt-0">
            <CreditRepairTab clientData={clientData} />
          </TabsContent>

          <TabsContent value="agent" className="mt-0">
            <AgentTab clientData={clientData} />
          </TabsContent>

          <TabsContent value="sessions" className="mt-0">
            <SessionsTab clientData={clientData} />
          </TabsContent>

          <TabsContent value="store" className="mt-0">
            <StoreTab clientData={clientData} />
          </TabsContent>

          <TabsContent value="vault" className="mt-0">
            <VaultTab clientData={clientData} />
          </TabsContent>

          <TabsContent value="budget" className="mt-0">
            <BudgetTab clientData={clientData} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
