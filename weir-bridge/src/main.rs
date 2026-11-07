use std::collections::BTreeMap;
use std::io::{self, BufRead, Write};
use std::sync::Arc;

use harper_core::linting::{Linter, Suggestion};
use harper_core::parsers::{IsolateEnglish, PlainEnglish};
use harper_core::spell::{FstDictionary, MergedDictionary, MutableDictionary};
use harper_core::weir::WeirLinter;
use harper_core::{DictWordMetadata, Document};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

#[derive(Deserialize)]
#[serde(tag = "method", rename_all = "snake_case")]
enum Request {
    Validate {
        source: String,
    },
    Configure {
        rules: BTreeMap<String, String>,
        words: Vec<String>,
    },
    Check {
        text: String,
        isolate_english: bool,
    },
}

#[derive(Serialize)]
struct Finding<'a> {
    rule: &'a str,
    start: usize,
    end: usize,
    text: String,
    message: String,
    suggestions: Vec<String>,
}

#[derive(Default)]
struct Worker {
    rules: BTreeMap<String, WeirLinter>,
    dictionary: MergedDictionary,
}

impl Worker {
    fn handle(&mut self, request: Request) -> Result<Value, String> {
        match request {
            Request::Validate { source } => {
                let mut rule = WeirLinter::new(&source).map_err(|e| e.to_string())?;
                let count = rule.count_tests();
                let failures: Vec<_> = rule
                    .run_tests()
                    .into_iter()
                    .map(|failure| json!({"expected": failure.expected, "got": failure.got}))
                    .collect();
                Ok(json!({"tests": count, "failures": failures, "description": rule.description()}))
            }
            Request::Configure { rules, words } => {
                let mut compiled = BTreeMap::new();
                for (name, source) in rules {
                    let rule = WeirLinter::new(&source).map_err(|e| format!("{name}: {e}"))?;
                    compiled.insert(name, rule);
                }
                let mut user = MutableDictionary::new();
                user.extend_words(words.into_iter().map(|word| {
                    (
                        word.chars().collect::<Vec<_>>(),
                        DictWordMetadata::default(),
                    )
                }));
                let mut dictionary = MergedDictionary::new();
                dictionary.add_dictionary(FstDictionary::curated());
                dictionary.add_dictionary(Arc::new(user));
                self.rules = compiled;
                self.dictionary = dictionary;
                Ok(Value::Null)
            }
            Request::Check {
                text,
                isolate_english,
            } => {
                let doc = if isolate_english {
                    let parser =
                        IsolateEnglish::new(Box::new(PlainEnglish), self.dictionary.clone());
                    Document::new(&text, &parser, &self.dictionary)
                } else {
                    Document::new_plain_english(&text, &self.dictionary)
                };
                let mut issues = Vec::new();
                for (rule, linter) in &mut self.rules {
                    for lint in linter.lint(&doc) {
                        let original = lint.get_str(doc.get_source());
                        let suggestions = lint
                            .suggestions
                            .into_iter()
                            .map(|suggestion| match suggestion {
                                Suggestion::ReplaceWith(chars) => chars.into_iter().collect(),
                                Suggestion::InsertAfter(chars) => {
                                    original.chars().chain(chars).collect()
                                }
                                Suggestion::Remove => String::new(),
                            })
                            .collect();
                        issues.push(Finding {
                            rule,
                            start: lint.span.start,
                            end: lint.span.end,
                            text: original,
                            message: lint.message,
                            suggestions,
                        });
                    }
                }
                serde_json::to_value(issues).map_err(|e| e.to_string())
            }
        }
    }
}

fn main() -> io::Result<()> {
    if std::env::args().nth(1).as_deref() == Some("--version") {
        println!("libreharp-weir {}", harper_core::core_version());
        return Ok(());
    }
    let mut worker = Worker::default();
    let mut out = io::BufWriter::new(io::stdout().lock());
    for line in io::stdin().lock().lines() {
        let result = serde_json::from_str(&line?)
            .map_err(|e| e.to_string())
            .and_then(|request| worker.handle(request));
        let response = match result {
            Ok(value) => json!({"result": value}),
            Err(error) => json!({"error": error}),
        };
        serde_json::to_writer(&mut out, &response)?;
        out.write_all(b"\n")?;
        out.flush()?;
    }
    Ok(())
}
