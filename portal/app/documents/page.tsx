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

const CATEGORY_ICONS: Record<string, string> = {
  identity: "🪪",
  credit_report: "📊",
  dispute_evidence: "📋",
  signed_agreement: "✍️",
  general: "📄",
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
            <div className="text-4xl mb-2">{uploading ? "⏳" : "📁"}</div>
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
                <p className="text-3xl mb-2">📁</p>
                <p>No documents found</p>
              </div>
            )}
            {filtered.map((doc) => (
              <div key={doc.id} className="flex items-center gap-4 p-4 border-b border-gray-50 last:border-0 hover:bg-gray-50">
                <div className="text-2xl">{CATEGORY_ICONS[doc.category] || "📄"}</div>
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
                    {doc.status === "verified" ? "✓ Verified" : "⧗ Pending"}
                  </span>
                  <button
                    onClick={() => window.open(`/documents/preview/${doc.id}`, "_blank")}
                    className="text-gray-400 hover:text-[#1a2744] p-1"
                    title="Preview"
                  >
                    👁️
                  </button>
                  <button
                    onClick={() => setDeleteId(doc.id)}
                    className="text-gray-400 hover:text-red-500 p-1"
                    title="Delete"
                  >
                    🗑️
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
