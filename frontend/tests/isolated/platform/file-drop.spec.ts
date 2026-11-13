import { expect, test } from "@playwright/test";

import { checkDroppedFiles } from "../../../src/lib/file-drop";

// A dropped or pasted file takes the checks of "Choose file" before the
// upload (SI-7.3, DR-SI-7.3): one file at a time, nothing while the panel's
// one operation runs (its words name the kind: an upload, or any other
// operation such as a download, an archive, a status check or "Load more"),
// the picker's types (its `accept` list is no check for a drop), and the
// size limit. The http journeys in tests/http/record-file-drop.spec.ts show
// one message of each kind on the panels.

const MAX = 25 * 1024 * 1024;
const pdf = { name: "Quote.pdf", size: 4 };

test("SI-C7.3 several files, or a running upload or other operation, refuse the drop before any file check", () => {
  const two = [pdf, { name: "Terms.pdf", size: 4 }];
  for (const row of [
    { files: two, running: null, message: "Drop one file at a time." },
    // Several files say so even while an operation runs.
    { files: two, running: "upload", message: "Drop one file at a time." },
    { files: two, running: "other", message: "Drop one file at a time." },
    {
      files: [pdf],
      running: "upload",
      message: "Wait for the current upload to finish.",
    },
    {
      // A download, an archive, a status check or "Load more".
      files: [pdf],
      running: "other",
      message: "Wait a moment, then drop the file again.",
    },
    {
      // A running operation refuses a file that the type check would refuse.
      files: [{ name: "notes.txt", size: 4 }],
      running: "upload",
      message: "Wait for the current upload to finish.",
    },
    {
      files: [{ name: "notes.txt", size: 4 }],
      running: "other",
      message: "Wait a moment, then drop the file again.",
    },
  ] as const)
    expect(
      checkDroppedFiles(row.files, row.running),
      JSON.stringify(row),
    ).toEqual({ message: row.message });
});

test("SI-C7.3 only the picker's file types pass, whatever the letter case", () => {
  for (const name of [
    "Quote.pdf",
    "Yard.png",
    "Photo.jpg",
    "Photo.jpeg",
    "Terms.docx",
    "Prices.xlsx",
    "Deck.pptx",
    "SCAN.PDF",
    "Photo.JpEg",
    "quote.v2.pdf",
  ])
    expect(checkDroppedFiles([{ name, size: 4 }], null), name).toEqual({
      file: { name, size: 4 },
    });
  for (const name of [
    "notes.txt",
    "setup.exe",
    "quote.pdf.exe",
    "archive.zip",
    "Terms.doc",
    "README",
    "pdf",
    "quote.pdf ",
  ])
    expect(checkDroppedFiles([{ name, size: 4 }], null), name).toEqual({
      message: "Choose a PDF, PNG, JPEG, Word, Excel, or PowerPoint file.",
    });
});

test("SI-C7.3 the size limit of Choose file holds for a dropped file", () => {
  for (const [size, passes] of [
    [0, false],
    [1, true],
    [MAX, true],
    [MAX + 1, false],
  ] as const)
    expect(checkDroppedFiles([{ name: "Quote.pdf", size }], null)).toEqual(
      passes
        ? { file: { name: "Quote.pdf", size } }
        : {
            message:
              "Choose a file larger than 0 bytes and no larger than 25 MB.",
          },
    );
});

test("SI-C7.3 a drop or paste without a file asks nothing", () => {
  expect(checkDroppedFiles([], null)).toBeNull();
  expect(checkDroppedFiles([], "upload")).toBeNull();
  expect(checkDroppedFiles([], "other")).toBeNull();
});
