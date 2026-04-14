"use client";

import { useState, useRef } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { api, Document } from "@/lib/api";

const CATEGORIES = ["all", "identity", "credit_report", "dispute_evidence", "signed_agreement", "general"];

const MOCK_DOCS: Document[] = [
  { id: "d1", name: "Credit_Report_Equifax_Apr2026.pdf", category: "credit_report", status: "verified", uploaded_at: new Date(Date.now() - 86400000 * 3).toISOString() },
  { id: "d2", name: "Drivers_License.jpg", category: "identity", status: "verified", uploaded_at: new Date(Date.now() - 86400000 * 10).toISOString() },
  { id: "d3", name: "Dispute_Evidence_CapOne.pdf", category: "dispute_evidence", status: "pending", uploaded_at: new Date().toISOString() },
];

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  identity: <svg className="w-6 h-6 text-[#1a2744]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V8a2 2 0 00-2-2h-5m-4 0V5a2 2 0 114 0v1m-4 0a2 2 0 104 0m-5 8a2 2 0 100-4 2 2 0 000 4zm0 0c0 1.306.84 2.417 2 2.83" /></svg>,
  credit_report: <svg className="w-6 h-6 text-[#1a2744]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>,
  dispute_evidence: <svg className="w-6 h-6 text-[#1a2744]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>,
  signed_agreement: <svg className="w-6 h-6 text-[#1a2744]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" /></svg>,
  general: <svg className="w-6 h-6 text-[#1a2744]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>,
};

export default function DocumentsPage() {
  const [docs, setDocs] = useState<Document[]>(MOCK_DOCS);
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [uploading, setUploading] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const filtered = categoryFilter === "all" ? docs : docs.filter((d) => d.category === categoryFilter);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    const allowed = ["application/pdf", "image/jpeg", "image/png", "image/webp"];
    if (!allowed.includes(file.type)) {
      alert("Only PDF and image files are allowed.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      alert("File too large. Maximum 10MB.");
      return;
    }

    setUploading(true);
    try {
      // Mock upload for demo
      const newDoc: Document = {
        id: Date.now().toString(),
        name: file.name,
        category: "general",
        status: "pending",
        uploaded_at: new Date().toISOString(),
      };
      setDocs((prev) => [...prev, newDoc]);
      alert(`"${file.name}" uploaded successfully!`);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handleDelete(docId: string) {
    try {
      await api.clients.deleteDocument(docId).catch(() => {});
      setDocs((prev) => prev.filter((d) => d.id !== docId));
      setDeleteId(null);
    } catch (e) {
      alert("Delete failed.");
    }
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col">
        <Header title="Documents" />
        <main className="flex-1 p-6 space-y-4">
          {/* Upload area */}
          <div
            className="bg-white border-2 border-dashed border-gray-300 rounded-xl p-8 text-center hover:border-[#c4922a] transition-colors cursor-pointer"
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const file = e.dataTransfer.files[0];
              if (file && fileRef.current) {
                const dt = new DataTransfer();
                dt.items.add(file);
                fileRef.current.files = dt.files;
                fileRef.current.dispatchEvent(new Event("change", { bubbles: true }));
              }
            }}
          >
            <div className="mb-2 flex justify-center">{uploading ? (
              <svg className="w-10 h-10 text-gray-400 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
            ) : (
              <svg className="w-10 h-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
            )}</div>
            <p className="text-[#1a2744] font-semibold">{uploading ? "Uploading..." : "Drop files here or click to upload"}</p>
            <p className="text-gray-400 text-sm mt-1">PDF, JPG, PNG up to 10MB</p>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.webp"
              className="hidden"
              onChange={handleUpload}
            />
          </div>

          {/* Category filter */}
          <div className="flex gap-2 flex-wrap">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => setCategoryFilter(cat)}
                className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition-colors ${
                  categoryFilter === cat
                    ? "bg-[#1a2744] text-white"
                    : "bg-white text-gray-600 border border-gray-200 hover:border-[#1a2744]"
                }`}
              >
                {cat === "all" ? "All" : cat.replace(/_/g, " ")}
              </button>
            ))}
          </div>

          {/* Document list */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
            {filtered.length === 0 && (
              <div className="p-12 text-center text-gray-400">
                <div className="flex justify-center mb-2"><svg className="w-10 h-10 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" /></svg></div>
                <p>No documents found</p>
              </div>
            )}
            {filtered.map((doc) => (
              <div key={doc.id} className="flex items-center gap-4 p-4 border-b border-gray-50 last:border-0 hover:bg-gray-50">
                <div className="flex items-center justify-center w-8 h-8">{CATEGORY_ICONS[doc.category] || <svg className="w-6 h-6 text-[#1a2744]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>}</div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-[#1a2744] truncate">{doc.name}</p>
                  <div className="flex gap-3 mt-0.5 text-xs text-gray-400">
                    <span className="capitalize">{doc.category.replace(/_/g, " ")}</span>
                    <span>Uploaded {new Date(doc.uploaded_at).toLocaleDateString()}</span>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${
                    doc.status === "verified"
                      ? "bg-green-100 text-green-700"
                      : "bg-yellow-100 text-yellow-700"
                  }`}>
                    {doc.status === "verified" ? "Verified" : "Pending"}
                  </span>
                  <button
                    onClick={() => window.open(`/documents/preview/${doc.id}`, "_blank")}
                    className="text-gray-400 hover:text-[#1a2744] p-1"
                    title="Preview"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
                  </button>
                  <button
                    onClick={() => setDeleteId(doc.id)}
                    className="text-gray-400 hover:text-red-500 p-1"
                    title="Delete"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </main>
      </div>

      {/* Delete confirmation modal */}
      {deleteId && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl">
            <h3 className="text-lg font-bold text-[#1a2744] mb-2">Delete Document?</h3>
            <p className="text-gray-500 text-sm mb-4">This action cannot be undone.</p>
            <div className="flex gap-3">
              <button
                onClick={() => setDeleteId(null)}
                className="flex-1 border border-gray-200 text-gray-600 py-2.5 rounded-lg font-medium"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteId)}
                className="flex-1 bg-red-600 text-white py-2.5 rounded-lg font-medium hover:bg-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
