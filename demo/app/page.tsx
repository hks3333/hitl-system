"use client";

import { useMemo, useState } from "react";

type Reply = {
  id: string;
  content: string;
  createdAt: string;
};

type Post = {
  id: string;
  content: string;
  createdAt: string;
  replies: Reply[];
  showReply?: boolean;
  replyDraft?: string;
  submitting?: boolean;
};

function rid() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return (crypto as Crypto).randomUUID();
  }
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

async function sendToBackend(content_id: string, content_text: string) {
  try {
    await fetch("http://127.0.0.1:8000/workflows/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content_id, content_text }),
    });
  } catch {}
}

export default function Home() {
  const initialPosts = useMemo<Post[]>(
    () => [
      {
        id: rid(),
        content: "Welcome to the company forum. Share updates, questions, and ideas.",
        createdAt: new Date().toISOString(),
        replies: [
          {
            id: rid(),
            content: "Thanks for setting this up!",
            createdAt: new Date().toISOString(),
          },
        ],
      },
      {
        id: rid(),
        content: "Quarterly planning kicks off next week. Post topics you want covered.",
        createdAt: new Date().toISOString(),
        replies: [],
      },
    ],
    []
  );

  const [posts, setPosts] = useState<Post[]>(initialPosts);
  const [newPost, setNewPost] = useState("");
  const [submittingPost, setSubmittingPost] = useState(false);

  async function handleCreatePost() {
    const text = newPost.trim();
    if (!text) return;
    setSubmittingPost(true);
    const id = rid();
    const optimistic: Post = {
      id,
      content: text,
      createdAt: new Date().toISOString(),
      replies: [],
    };
    setPosts((p) => [optimistic, ...p]);
    setNewPost("");
    await sendToBackend(id, text);
    setSubmittingPost(false);
  }

  function toggleReply(postId: string) {
    setPosts((p) =>
      p.map((post) =>
        post.id === postId
          ? { ...post, showReply: !post.showReply, replyDraft: post.replyDraft ?? "" }
          : post
      )
    );
  }

  function onReplyDraftChange(postId: string, value: string) {
    setPosts((p) =>
      p.map((post) => (post.id === postId ? { ...post, replyDraft: value } : post))
    );
  }

  async function handleSubmitReply(postId: string) {
    const post = posts.find((x) => x.id === postId);
    const text = (post?.replyDraft || "").trim();
    if (!post || !text) return;
    const replyId = rid();
    const optimistic: Reply = {
      id: replyId,
      content: text,
      createdAt: new Date().toISOString(),
    };
    setPosts((p) =>
      p.map((x) =>
        x.id === postId
          ? {
              ...x,
              replies: [...x.replies, optimistic],
              replyDraft: "",
              showReply: false,
            }
          : x
      )
    );
    await sendToBackend(replyId, text);
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b bg-white">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-semibold tracking-tight text-gray-900">Company Forum</h1>
            <div className="text-sm text-gray-500">Stay aligned. Share openly.</div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <section className="lg:col-span-2 space-y-6">
            <div className="rounded-xl border bg-white p-4 shadow-sm">
              <h2 className="mb-3 text-base font-medium text-gray-900">Create a new post</h2>
              <div className="space-y-3">
                <textarea
                  value={newPost}
                  onChange={(e) => setNewPost(e.target.value)}
                  placeholder="Share an update, ask a question, or start a discussion..."
                  rows={4}
                  className="w-full resize-y rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none ring-0 transition focus:border-gray-900 focus:ring-2 focus:ring-gray-900/10"
                />
                <div className="flex items-center justify-end">
                  <button
                    type="button"
                    onClick={handleCreatePost}
                    disabled={submittingPost || newPost.trim().length === 0}
                    className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/40 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {submittingPost ? "Submitting..." : "Submit Post"}
                  </button>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              {posts.map((post) => (
                <article key={post.id} className="rounded-xl border bg-white p-4 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1">
                      <p className="text-sm leading-6 text-gray-900">{post.content}</p>
                      <div className="mt-2 text-xs text-gray-500">
                        {new Date(post.createdAt).toLocaleString()}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => toggleReply(post.id)}
                      className="h-8 shrink-0 rounded-md border border-gray-300 bg-white px-3 text-xs font-medium text-gray-700 transition hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/40"
                    >
                      {post.showReply ? "Cancel" : "Reply"}
                    </button>
                  </div>

                  {post.replies.length > 0 && (
                    <div className="mt-4 space-y-3 border-t pt-4">
                      {post.replies.map((r) => (
                        <div key={r.id} className="rounded-lg bg-gray-50 p-3">
                          <p className="text-sm leading-6 text-gray-800">{r.content}</p>
                          <div className="mt-1 text-xs text-gray-500">
                            {new Date(r.createdAt).toLocaleString()}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {post.showReply && (
                    <div className="mt-4 space-y-3 rounded-lg bg-gray-50 p-3">
                      <textarea
                        value={post.replyDraft ?? ""}
                        onChange={(e) => onReplyDraftChange(post.id, e.target.value)}
                        placeholder="Write a reply..."
                        rows={3}
                        className="w-full resize-y rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none ring-0 transition focus:border-gray-900 focus:ring-2 focus:ring-gray-900/10"
                      />
                      <div className="flex items-center justify-end">
                        <button
                          type="button"
                          onClick={() => handleSubmitReply(post.id)}
                          disabled={!post.replyDraft || post.replyDraft.trim().length === 0}
                          className="inline-flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/40 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          Submit Reply
                        </button>
                      </div>
                    </div>
                  )}
                </article>
              ))}
            </div>
          </section>

          <aside className="space-y-4">
            <div className="rounded-xl border bg-white p-4 shadow-sm">
              <h2 className="text-base font-medium text-gray-900">Forum Guide</h2>
              <ul className="mt-3 space-y-2 text-sm text-gray-700">
                <li className="leading-6">Be clear and concise.</li>
                <li className="leading-6">Share context and examples.</li>
                <li className="leading-6">Be respectful and supportive.</li>
              </ul>
            </div>
            <div className="rounded-xl border bg-white p-4 shadow-sm">
              <h2 className="text-base font-medium text-gray-900">Shortcuts</h2>
              <ul className="mt-3 space-y-2 text-sm text-gray-700">
                <li className="leading-6">Use the Reply button to respond inline.</li>
                <li className="leading-6">Your posts submit optimistically.</li>
                <li className="leading-6">All data posts to the backend endpoint.</li>
              </ul>
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}
