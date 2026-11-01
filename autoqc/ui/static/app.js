const e = React.createElement;

function actionClass(action) {
  const value = action || "";
  if (value.indexOf("FIX") >= 0) return "fix";
  if (value.indexOf("SEND") >= 0) return "send";
  if (value === "REJECT") return "reject";
  if (value === "ESCALATE") return "escalate";
  return "approve";
}

function fmt(seconds) {
  if (seconds == null || Number.isNaN(seconds)) return "--:--";
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return String(minutes).padStart(2, "0") + ":" + String(secs).padStart(2, "0");
}

function markersOf(review) {
  const marks = [];
  (review.checks || []).forEach(function (check) {
    (check.evidence || []).forEach(function (item) {
      if (item.start != null) marks.push({ t: item.start, label: check.title });
    });
  });
  (review.actions || []).forEach(function (action) {
    marks.push({ t: action.t, label: action.kind + " " + (action.target || "") });
  });
  marks.sort(function (a, b) { return a.t - b.t; });
  return marks;
}

function App() {
  const [reviews, setReviews] = React.useState([]);
  const [current, setCurrent] = React.useState(null);
  const [path, setPath] = React.useState("");
  const [time, setTime] = React.useState(0);
  const [error, setError] = React.useState("");

  function refresh() {
    return fetch("/api/reviews").then(function (response) { return response.json(); }).then(setReviews);
  }

  React.useEffect(function () { refresh(); }, []);

  function openReview(id) {
    fetch("/api/reviews/" + id).then(function (response) { return response.json(); }).then(function (payload) {
      setCurrent(payload);
      setTime(0);
    });
  }

  function runReview(event) {
    event.preventDefault();
    setError("");
    fetch("/api/reviews", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ submission_path: path }),
    }).then(function (response) {
      if (!response.ok) throw new Error("Could not review that folder");
      return response.json();
    }).then(function (payload) {
      setCurrent(payload);
      setTime(0);
      return refresh();
    }).catch(function (err) { setError(err.message); });
  }

  function copy(text) {
    if (navigator.clipboard) navigator.clipboard.writeText(text || "");
  }

  const words = current && current.stats && current.stats.transcript ? current.stats.transcript.words || [] : [];
  const marks = current ? markersOf(current) : [];

  return e("div", { className: "app" },
    e("header", { className: "top" },
      e("div", null,
        e("h1", null, "Auto QC"),
        e("div", { className: "banner" }, "A human reviewer makes the final call. Nothing is sent automatically.")
      ),
      current ? e("span", { className: "action " + actionClass(current.recommended_action) }, current.recommended_action || "APPROVE") : null
    ),
    e("form", { className: "run", onSubmit: runReview },
      e("input", {
        type: "text",
        placeholder: "Path to a submission folder",
        value: path,
        onChange: function (event) { setPath(event.target.value); },
        "aria-label": "Submission folder",
      }),
      e("button", { type: "submit" }, "Review")
    ),
    error ? e("p", null, error) : null,
    e("div", { className: "layout" },
      e("aside", { className: "panel" },
        e("strong", null, "Saved reviews"),
        e("ul", { className: "review-list" },
          reviews.map(function (item) {
            return e("li", { key: item.id },
              e("button", { type: "button", onClick: function () { openReview(item.id); } },
                "#" + item.id + " " + (item.action || "review")
              )
            );
          })
        )
      ),
      current ? e("main", null, ReviewView({ review: current, time: time, setTime: setTime, words: words, marks: marks, copy: copy })) : e("main", { className: "panel" }, "Run a folder or open a saved review.")
    )
  );
}

function ReviewView(props) {
  const review = props.review;
  const checks = (review.checks || []).slice().sort(function (a, b) { return (a.item || 99) - (b.item || 99); });
  const typing = review.stats && review.stats.typing_percent != null ? review.stats.typing_percent.toFixed(2) + "%" : "n/a";
  const coverage = review.stats && review.stats.narration_coverage != null ? Math.round(review.stats.narration_coverage * 100) + "%" : "n/a";
  return e("div", null,
    e("section", { className: "card" },
      e("h2", null, "Why this action"),
      e("ul", null, (review.reasons || []).map(function (reason, index) { return e("li", { key: index }, reason); })),
      (review.needs_human || []).length ? e("div", { className: "human" },
        e("strong", null, "Needs human look"),
        e("ul", null, review.needs_human.map(function (item, index) {
          return e("li", { key: index }, item.summary);
        }))
      ) : null
    ),
    e("div", { className: "grid" },
      e("section", { className: "card" },
        e("h2", null, "Scorecard"),
        e("p", null, "Typing " + typing + " · Narration coverage " + coverage),
        checks.map(function (check) {
          return e("div", { className: "score", key: check.key },
            e("div", null,
              e("strong", null, (check.item || "–") + ". " + check.title),
              e("div", null, check.summary)
            ),
            e("div", { className: "band" }, check.band == null ? "—" : "B" + check.band)
          );
        })
      ),
      e("section", { className: "card player" },
        e("h2", null, "Recording"),
        e("img", {
          alt: "Frame at " + fmt(props.time),
          src: "/api/reviews/" + review.id + "/frame?t=" + props.time,
        }),
        e("div", { className: "markers" },
          props.marks.map(function (mark, index) {
            return e("button", {
              type: "button",
              key: index,
              onClick: function () { props.setTime(mark.t); },
            }, fmt(mark.t) + " " + mark.label);
          })
        ),
        e("h3", null, "Transcript"),
        e("div", { className: "transcript" },
          props.words.length ? props.words.map(function (word, index) {
            const on = props.time >= word.start && props.time <= word.end + 0.4;
            return e("span", { key: index, className: on ? "on" : "" }, word.word + " ");
          }) : "No transcript loaded."
        )
      )
    ),
    e("section", { className: "card" },
      e("h2", null, "Findings"),
      e("table", null,
        e("thead", null, e("tr", null, e("th", null, "When"), e("th", null, "Action"), e("th", null, "Summary"), e("th", null, "Frame"))),
        e("tbody", null, (review.findings || []).map(function (finding, index) {
          const start = finding.evidence && finding.evidence[0] ? finding.evidence[0].start : null;
          return e("tr", { key: index },
            e("td", null, fmt(start)),
            e("td", null, finding.action),
            e("td", null, finding.summary),
            e("td", null, start == null ? null : e("img", {
              alt: "",
              src: "/api/reviews/" + review.id + "/frame?t=" + start,
            }))
          );
        }))
      )
    ),
    e("section", { className: "card drafts" },
      e("h2", null, "Drafts"),
      ["studio_feedback", "send_back", "internal_notes", "slack_dm", "growth_notes"].map(function (key) {
        const text = (review.drafts && review.drafts[key]) || "";
        return e("div", { key: key },
          e("h3", null, key.replaceAll("_", " ")),
          e("textarea", { readOnly: true, value: text }),
          e("button", { type: "button", className: "ghost", onClick: function () { props.copy(text); } }, "Copy")
        );
      }),
      review.corrected_metadata_rtf ? e("p", null, e("a", { href: "/api/reviews/" + review.id + "/metadata.rtf" }, "Download corrected Metadata.rtf")) : null,
      (review.rename_suggestions || []).length ? e("ul", null, review.rename_suggestions.map(function (item, index) {
        return e("li", { key: index }, item.actual + " → " + item.expected);
      })) : null
    ),
    review.prior_diff ? e("section", { className: "card" },
      e("h2", null, "Diff vs prior submission"),
      e("p", null, review.prior_diff.unchanged ? "No meaningful change from the prior submission." : "This resubmission differs from the prior one."),
      e("p", null, "Text similarity " + review.prior_diff.text_similarity),
      e("p", null, "Added files: " + ((review.prior_diff.deliverables_added || []).join(", ") || "none")),
      e("p", null, "Removed files: " + ((review.prior_diff.deliverables_removed || []).join(", ") || "none"))
    ) : null
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(e(App));
