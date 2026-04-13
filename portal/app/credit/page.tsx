"use client";

import { useState, useEffect } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { api } from "@/lib/api";

type Bureau = "all" | "equifax" | "experian" | "transunion";

interface CreditItem {
  id: string;
  creditor: string;
  amount?: number;
  status: string;
  date?: string;
  bureau?: string;
  account_type?: string;
  payment_status?: string;
  type?: string;
}

const MOCK_NEGATIVE = [
  { id: "n1", creditor: "Capital One", amount: 2340, status: "charge_off", date: "2022-03-15", bureau: "equifax", type: "credit_card" },
  { id: "n2", creditor: "LVNV Funding LLC", amount: 890, status: "collection", date: "2021-11-20", bureau: "transunion", type: "collection" },
  { id: "n3", creditor: "Synchrony Bank", amount: 650, status: "late_90", date: "2023-01-08", bureau: "experian", type: "credit_card" },
];
const MOCK_TRADELINES = [
  { id: "t1", creditor: "Chase", amount: 0, status: "current", bureau: "all", account_type: "credit_card", payment_status: "current" },
  { id: "t2", creditor: "Discover", amount: 1200, status: "current", bureau: "all", account_type: "credit_card", payment_status: "current" },
];
const MOCK_INQUIRIES: CreditItem[] = [
  { id: "i1", creditor: "AutoNation", date: "2023-08-12", bureau: "equifax", type: "hard", status: "inquiry" },
  { id: "i2", creditor: "Capital One", date: "2023-06-01", bureau: "experian", type: "hard", status: "inquiry" },
];

export default function CreditPage() {
  const [activeTab, setActiveTab] = useState<"negative" | "tradelines" | "inquiries">("negative");
  const [bureauFilter, setBureauFilter] = useState<Bureau>("all");
  const [loading, setLoading] = useState(false);
  const [negativeItems, setNegativeItems] = useState<CreditItem[]>(MOCK_NEGATIVE);
  const [tradelines, setTradelines] = useState<CreditItem[]>(MOCK_TRADELINES);
  const [inquiries, setInquiries] = useState<CreditItem[]>(MOCK_INQUIRIES);

  function getStatusColor(status: string) {
    if (["current", "paid"].includes(status)) return "bg-green-100 text-green-700";
    if (["late_30", "late_60"].includes(status)) return "bg-yellow-100 text-yellow-700";
    if (["late_90", "charge_off", "collection"].includes(status)) return "bg-red-100 text-red-700";
    return "bg-gray-100 text-gray-600";
  }

  const filterByBureau = (items: CreditItem[]) =>
    bureauFilter === "all" ? items : items.filter((i) => !i.bureau || i.bureau === bureauFilter || i.bureau === "all");

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <Header title="Credit Report" />
        <main className="flex-1 p-6 space-y-4">
          {/* Bureau filter */}
          <div className="flex gap-2 flex-wrap">
            {(["all", "equifax", "experian", "transunion"] as Bureau[]).map((bureau) => (
              <button
                key={bureau}
                onClick={() => setBureauFilter(bureau)}
                className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition-colors ${
                  bureauFilter === bureau
                    ? "bg-[#1a2744] text-white"
                    : "bg-white text-gray-600 border border-gray-200 hover:border-[#1a2744]"
                }`}
              >
                {bureau === "all" ? "All Bureaus" : bureau}
              </button>
            ))}
            <button
              className="ml-auto bg-[#c4922a] text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-[#d9a84e]"
              onClick={() => alert("Pulling soft credit report... (Demo)")}
            >
              🔄 Pull New Report
            </button>
          </div>

          {/* Tabs */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="flex border-b border-gray-100">
              {[
                { key: "negative", label: `Negative Items (${filterByBureau(negativeItems).length})` },
                { key: "tradelines", label: `Tradelines (${filterByBureau(tradelines).length})` },
                { key: "inquiries", label: `Inquiries (${filterByBureau(inquiries).length})` },
              ].map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key as typeof activeTab)}
                  className={`px-6 py-4 text-sm font-medium border-b-2 transition-colors ${
                    activeTab === tab.key
                      ? "border-[#c4922a] text-[#c4922a]"
                      : "border-transparent text-gray-500 hover:text-gray-700"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Negative Items */}
            {activeTab === "negative" && (
              <div className="divide-y divide-gray-50">
                {filterByBureau(negativeItems).map((item) => (
                  <div key={item.id} className="p-5 flex items-center justify-between hover:bg-gray-50">
                    <div className="flex-1">
                      <div className="flex items-center gap-3">
                        <p className="font-semibold text-[#1a2744]">{item.creditor}</p>
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(item.status)}`}>
                          {item.status?.replace(/_/g, " ")}
                        </span>
                        {item.bureau && (
                          <span className="text-xs text-gray-400 capitalize">{item.bureau}</span>
                        )}
                      </div>
                      <div className="flex gap-4 mt-1 text-sm text-gray-500">
                        {item.amount && <span>${item.amount.toLocaleString()}</span>}
                        {item.date && <span>Reported: {new Date(item.date).toLocaleDateString()}</span>}
                        {item.type && <span className="capitalize">{item.type.replace(/_/g, " ")}</span>}
                      </div>
                    </div>
                    <button
                      className="bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-red-700 transition-colors"
                      onClick={() => alert(`Starting dispute for ${item.creditor}...`)}
                    >
                      Dispute This
                    </button>
                  </div>
                ))}
                {filterByBureau(negativeItems).length === 0 && (
                  <div className="p-12 text-center text-gray-400">No negative items found</div>
                )}
              </div>
            )}

            {/* Tradelines */}
            {activeTab === "tradelines" && (
              <div className="divide-y divide-gray-50">
                {filterByBureau(tradelines).map((item) => (
                  <div key={item.id} className="p-5 flex items-center justify-between hover:bg-gray-50">
                    <div>
                      <div className="flex items-center gap-3">
                        <p className="font-semibold text-[#1a2744]">{item.creditor}</p>
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${getStatusColor(item.payment_status || item.status)}`}>
                          {(item.payment_status || item.status)?.replace(/_/g, " ")}
                        </span>
                      </div>
                      <div className="flex gap-4 mt-1 text-sm text-gray-500">
                        {item.amount !== undefined && <span>Balance: ${item.amount.toLocaleString()}</span>}
                        {item.account_type && <span className="capitalize">{item.account_type.replace(/_/g, " ")}</span>}
                      </div>
                    </div>
                    <span className="text-green-600 text-sm">✓ Good standing</span>
                  </div>
                ))}
              </div>
            )}

            {/* Inquiries */}
            {activeTab === "inquiries" && (
              <div className="divide-y divide-gray-50">
                {filterByBureau(inquiries).map((item) => (
                  <div key={item.id} className="p-5 flex items-center justify-between hover:bg-gray-50">
                    <div>
                      <p className="font-semibold text-[#1a2744]">{item.creditor}</p>
                      <div className="flex gap-4 mt-1 text-sm text-gray-500">
                        {item.date && <span>Date: {new Date(item.date).toLocaleDateString()}</span>}
                        {item.bureau && <span className="capitalize">{item.bureau}</span>}
                        <span className="capitalize">{item.type} inquiry</span>
                      </div>
                    </div>
                    <button
                      className="border border-red-300 text-red-600 px-3 py-1.5 rounded-lg text-sm hover:bg-red-50"
                      onClick={() => alert(`Disputing inquiry from ${item.creditor}...`)}
                    >
                      Dispute
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
