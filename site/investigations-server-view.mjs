import { h } from "./dom.mjs";
import { ReviewApi } from "./investigations-api.mjs";
import { assessmentDraft } from "./investigations-reviews.mjs";
import { assessmentEditor } from "./investigations-assessment-view.mjs";

const api = new ReviewApi();
const drafts = new Map();
let available = false;
export const probeServerReviews = async () => { available = await api.available(); return available; };
export const hasServerDrafts = () => [...drafts.values()].some((s) => s.dirty);
const command = (text, action) => h("button", { type: "button", class: "btn", onclick: action }, text);

export function serverReviewPanel(event) {
  if (!available) return null;
  const details = h("details", { class: "server-review" }, h("summary", {}, "Server review (optional)"));
  details.append(h("p", { class: "notice failure" }, "Free demo: server reviews are temporary and may be lost on restart or redeploy. Browser-local reviews remain separate on this device. Server saves do not verify a fire."));
  const status = h("p", { role: "status", "aria-live": "polite", class: "review-time" });
  const content = h("div", { class: "review-form" }); details.append(status, content);
  const tell = (text) => { status.textContent = text; };
  function render() {
    content.replaceChildren();
    if (!api.actor) {
      const username = h("input", { autocomplete: "username", maxlength: 80, required: true });
      const password = h("input", { type: "password", autocomplete: "current-password", maxlength: 1024, required: true });
      const submit = h("button", { class: "btn", type: "submit" }, "Sign in to server");
      const form = h("form", { class: "review-form", onsubmit: async (e) => {
        e.preventDefault(); submit.disabled = true;
        try { await api.login(username.value, password.value); password.value = ""; tell("Signed in. Session is held only in page memory."); render(); }
        catch (error) { password.value = ""; tell(error.message); }
        finally { submit.disabled = false; }
      } }, h("label", {}, "Username", username), h("label", {}, "Password", password), submit);
      content.append(form); return;
    }
    content.append(h("p", {}, `Signed in: ${api.actor.username} (${api.actor.role})`), command("Sign out", async () => {
      try { await api.logout(); tell("Signed out."); } catch (error) { tell(`${error.message}. Local session cleared.`); }
      render();
    }));
    const scope = event.provenance.feed === "national" ? "india" : "global";
    const key = `${api.actor.username}:${scope}:${event.id}`;
    let state = drafts.get(key);
    if (!state) { state = { version: null, notes: "", bookmarked: false, status: "unreviewed", ...assessmentDraft(), dirty: false }; drafts.set(key, state); }
    let assessment = assessmentEditor(state, () => { state.dirty = true; tell("Unsaved server assessment."); }, { idPrefix: "server" });
    const notes = h("textarea", { id: "server-review-notes", "aria-label": "Server notes", rows: 6, maxlength: 16000, oninput: () => { state.notes = notes.value; state.dirty = true; tell("Unsaved server draft."); } }, state.notes);
    const bookmark = h("input", { type: "checkbox", onchange: () => { state.bookmarked = bookmark.checked; state.dirty = true; } }); bookmark.checked = state.bookmarked;
    const select = h("select", { id: "server-review-status", "aria-label": "Server status", onchange: () => { state.status = select.value; state.dirty = true; } }, ["unreviewed", "investigating", "reviewed"].map((s) => h("option", { value: s }, s))); select.value = state.status;
    const save = command("Save temporary server review", async () => {
      save.disabled = true; notes.disabled = bookmark.disabled = select.disabled = true;
      assessment.querySelectorAll("input, select, textarea").forEach((control) => { control.disabled = true; });
      try {
        const result = await api.review(event.id, scope, { version: state.version, review: { notes: state.notes, bookmarked: state.bookmarked, status: state.status, ...assessmentDraft(state) } });
        state.version = result.version; state.dirty = false;
        tell(`Temporary server save: version ${result.version}, actor ${String(result.actor)}, timestamp ${String(result.updated_at)}. Not saved locally.`);
      } catch (error) { tell(error.message); }
      finally {
        save.disabled = state.version === null; notes.disabled = bookmark.disabled = select.disabled = false;
        assessment.querySelectorAll("input, select, textarea").forEach((control) => { control.disabled = false; });
      }
    });
    save.disabled = state.version === null;
    const load = command("Load server version", async () => {
      load.disabled = true;
      const actor = api.actor;
      try {
        const result = await api.review(event.id, scope);
        if (api.actor !== actor) return;
        state.version = result.version;
        if (!state.dirty) {
          state.notes = result.review?.notes ?? ""; state.bookmarked = result.review?.bookmarked ?? false; state.status = result.review?.status ?? "unreviewed";
          Object.assign(state, assessmentDraft(result.review));
          notes.value = state.notes; bookmark.checked = state.bookmarked; select.value = state.status;
          const next = assessmentEditor(state, () => { state.dirty = true; tell("Unsaved server assessment."); }, { idPrefix: "server" });
          assessment.replaceWith(next); assessment = next;
        }
        save.disabled = false;
        tell(`Server version ${result.version}${state.dirty ? "; your draft retained. Saving will explicitly apply it to this version." : " loaded."}`);
      } catch (error) { tell(error.message); }
      finally { load.disabled = false; }
    });
    content.append(h("p", { class: "review-time" }, `Server key: ${scope} / ${event.id}`), load,
      h("label", {}, "Server status", select), h("label", { class: "check" }, bookmark, "Server bookmark"),
      h("label", {}, "Server notes", notes), assessment, save);
  }
  render(); return details;
}
