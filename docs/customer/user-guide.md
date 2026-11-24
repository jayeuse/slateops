# Slate Operations User Guide

This guide is for the people who use Slate Operations every day. It tells you how to find your way, work with records and sheets, use Boards, and send messages in OpenComms.

Your administrator sets up Slate Operations and gives you access. Administrator tasks, such as people, backups, and updates, are in the [Administrator guide](administrator-guide.md). To install and sign in for the first time, read the [Quick start](quick-start.md).

For help with Slate Operations, contact [support contact].

## How to use this guide

- Bold text is the exact name of a button, menu, tab, or page in the app.
- Each chapter names the source files of its screen names in a short bracket under the title. You do not need these files. They help your administrator and support check the guide.
- Your organization chooses its own department, module, and board names. This guide calls them "your department", "a module", and "a project board".
- What you see depends on your access. If a button in this guide is not on your screen, your access level does not include it. Ask your administrator.
- A statement marked "(unverified)" comes from the design of the app, not from a check of the screen. Tell your administrator if the screen is different.

### Words in this guide

| Word | Meaning |
|---|---|
| Organization | Your company in Slate Operations: its people, departments, records, and settings. |
| Department | The top unit of your organization, for example Sales. Each department has a Dashboard, an Announcements board, and modules. |
| Module | One kind of record in a department, for example Orders. Each module has its own page. |
| Record | One entry in a module, for example one order. |
| Field | One value on a record, for example a date or a status. |
| Sheet | Your own table of rows and columns on a record or a module. A sheet never changes the record. |
| Board | A shared page of posts and events. |
| Access level | What you can do in a department, module, or board. **Read** lets you open and view. **Write** also lets you add and change records. **Manage** also lets you change settings and access. |
| Guest | A person from outside the organization. A guest can only read. |

## 1. Getting around

[Source: `frontend/src/app/login/page.tsx`, `frontend/src/components/app-shell.tsx`, `frontend/src/components/app-navigation.tsx`, `frontend/src/components/workspace-navigation.ts`, `frontend/src/components/help/help-panel.tsx`, `frontend/src/components/settings/`]

### 1.1 Sign in

1. Open the Slate Operations address that your administrator gave you: [Slate Operations address].
2. On the **Welcome back** page, type your email or username in **Email or username**.
3. Type your password in **Password**.
4. Select **Sign in**.

Slate Operations opens your start page. You can change the start page in **Account settings** (see 1.5).

If you see "Finish setup using the link in your invitation email.", your account is not ready. Open the invitation email and follow its link.

If your organization requires two-step verification, Slate Operations asks you to set up an authenticator app. Follow the steps on the screen. (unverified: the exact screens at sign-in.)

### 1.2 Reset a forgotten password

1. On the **Welcome back** page, select **Forgot password?**.
2. Type your email address in **Email**.
3. Select **Request recovery**.
4. Open the recovery email and select its link.
5. On the **Choose a new password** page, type your new password in **New password**.
6. Select **Reset password**.

A password must have at least 12 characters.

If the email does not arrive, ask your administrator. The administrator can check the email setup.

### 1.3 The sidebar

The sidebar is on the left side of the screen. On a phone, select **Open navigation** at the top to show it.

The sidebar has three parts.

**Departments** lists each department that you can read. Select a department name to open its pages:

- **Dashboard** shows charts and numbers for the department.
- **Announcements** opens the department board (see chapter 4).
- Each module name opens the module page, where you find its records (see chapter 3).

**Tools** lists the tools that you can use. Most people see these:

- **Boards** opens **My calendar**, **Company**, each project board, and **All boards**.
- **Files** shows department documents.
- **Organization** shows the name, region, and look of your organization. Only administrators change them.
- **System health** tells you if Slate Operations works now.

Administrators also see **Sandbox**, **Access**, and **Manage** in Tools.

The foot of the sidebar has three rows:

- **My sheets** lists the sheets that you own and the sheets that people share with you (see 3.10).
- **OpenComms** opens your messages and channels (see chapter 5). A number shows how many messages you did not read.
- Your name and photo open your profile.

To make the sidebar narrow or wide, select the sidebar button at the top. (unverified: the button name changes with the state.)

### 1.4 The top bar

The top bar is on every page. From left to right, it shows the page name, then these controls:

| Control | What it does |
|---|---|
| **Search** | Opens a search panel. It finds records, people, posts, events, messages, and files that you can read. |
| **Notifications** (bell) | Shows changes that are important to you, for example a mention or a reminder. **Mark all as read** clears the count. |
| **Help** (question mark) | Opens the Help panel for the page (see 1.6). |
| **Account** (your photo) | Opens **Your profile**, **Account settings**, and **Sign out**. |

To search fast, press Ctrl+K (Windows) or Command+K (Mac). This works when **Use shortcuts** is on. In OpenComms, the same keys switch conversations.

### 1.5 Account settings

Account settings holds your own details. Open it from the **Account** menu.

| Part | What you change |
|---|---|
| **Identity** | Your photo, display name, job title, phone, bio, and sign-in email. |
| **Sign-in** | Your password, two-step verification, and your sessions. |
| **Appearance** | Your color mode, motion, keyboard shortcuts (**Use shortcuts**), and **Start page**. |
| **Regional** | Your timezone and your date, time, and week formats. |

To change your password:

1. Open **Account settings**.
2. In **Sign-in**, select **Change password**.
3. Type your password in **Current password**.
4. Type the new password in **New password**.
5. Select **Change password**.

### 1.6 The Help panel

Each page has a short guide in the app.

1. Select **Help** in the top bar.
2. Read **This page**. It gives the most important facts about the page that you have open.
3. Read **Keyboard shortcuts** for the keys that you can use.
4. Read **Contact your administrator** for the email and phone of your administrator.

To close the panel, select **Close Help**.

### 1.7 When something goes wrong

Sometimes Slate Operations cannot reach its server. Then a band under the top bar says "Slate Operations cannot reach its server." Changes that you make then may not save. Slate Operations tries again on its own. Wait until the band goes before you continue.

When an action fails, the message can show a **Reference** with eight characters. Select **Copy reference**. Give the reference to your administrator. It helps them find the cause.

### 1.8 Sign out

1. Select **Account** in the top bar.
2. Select **Sign out**.

If you have changes that you did not save, Slate Operations asks you first.

## 2. Sandbox

[Source: `frontend/src/components/workspace-navigation.ts`, `frontend/src/components/systems/sandbox/`, `frontend/src/components/help/page-guides.ts`]

Only administrators see the Sandbox. If you are not an administrator, read this chapter to know where your departments and records come from. Then go to chapter 3.

The Sandbox is where an administrator designs the organization: its departments, modules, fields, and triggers. The administrator works on a draft. People do not see the draft. When the draft is ready, the administrator publishes it. Then the new departments and modules appear for everyone with access.

### 2.1 The four sections

The Sandbox has four sections in the sidebar.

| Section | What it is for |
|---|---|
| **Build** | Lay out departments, modules, and fields on the canvas. Select an item to change it. |
| **Triggers** | Set rules that change a field on a record when something happens. |
| **Test** | Try the design with values that you type. A test never creates records. |
| **History** | See earlier versions of the design. Compare two versions, or restore one into the draft. |

### 2.2 Status of the draft

The page header shows the status of the draft:

- **Nothing to publish yet**: the draft has no departments or modules.
- **Not published yet**: the draft has content, and nobody published it.
- **Unpublished changes**: the draft is different from what people use now.
- **Published**: the draft and what people use are the same.

### 2.3 Add a department

1. Open **Sandbox** and select **Build**.
2. Select **Add department**.
3. Type the department name.
4. Add modules and fields with the controls on the department.

Slate Operations saves the draft as you work.

### 2.4 Add a trigger

A trigger changes a field on its own record when an event occurs. Only this kind of trigger works today.

1. Select **Triggers**.
2. Select **New trigger**.
3. Set when it runs, what it checks, and what it does.
4. Select **Save triggers**.

To try a trigger before you publish, open **Test** and select **Try this trigger**. The result shows **Test only · live data unchanged**.

### 2.5 Save a checkpoint

A checkpoint is a named copy of the draft. Use it before a large change.

1. Select **More Sandbox actions**.
2. Select **Save checkpoint**.
3. Type a name in **Checkpoint name**.
4. Select **Save checkpoint**.

### 2.6 Publish the draft

Caution: publish changes what all people in your organization see. Check the review before you publish.

1. Select **Review & Publish**.
2. If the dialog shows **Review changes**, select it.
3. Read the list of changes.
4. Type your administrator password.
5. Select **Publish changes**.

## 3. OpenView: records, dashboards, reports, and sheets

[Source: `frontend/src/components/systems/openview/components/` (mainly `module-page-switch.tsx`, `server-backed-views-workspace.tsx`, `record-create-dialog.tsx`, `record-details-controls.tsx`, `record-selection-bar.tsx`, `export-dialog.tsx`, `module-reports.tsx`, `report-detail.tsx`, `server-backed-dashboards.tsx`, `sheet-lists.tsx`, `my-sheets.tsx`, `sheet-header-actions.tsx`, `sheet-grid-view.tsx`, `sheet-column-form.tsx`, `sheet-share-dialog.tsx`), `frontend/src/components/systems/shared/components/record-sheet.tsx`, `frontend/src/components/systems/access/components/access-toolbar.tsx`]

OpenView is the part of Slate Operations that shows your records. It has no row of its own in the sidebar. You open it through your department in **Departments**.

### 3.1 Open a module page

1. In the sidebar, under **Departments**, select your department.
2. Select the module name, for example Orders.

The module page has three tabs:

- **Records** lists the records of the module.
- **Reports** keeps saved reports of the module.
- **Sheets** lists the sheets on the module.

The number next to a tab tells you how many items it holds.

### 3.2 Find a record

Use the bar above the list.

1. Type a word in **Search**. The list shows the records that match.
2. To sort, choose an order in the sort list.
3. To filter, select **Filters** and add a condition.
4. To remove all filters, clear them in the **Showing** line above the list.

To change how the list looks, choose **Table**, **Grid**, or **Gallery** in the layout menu. To choose which fields show, select **Columns**.

A saved view is a stored search, filter, and layout. To use one, choose it in **View**. **All records** shows the records with no saved view.

People with **Manage** on the module can save a view. They use **Save view** or **Save as new view**. All readers of the module then see it.

### 3.3 Open and read a record

1. Select a row in the list.
2. Read the record in the panel that opens.

The record panel has these tabs:

| Tab | What it shows |
|---|---|
| **Details** | The fields of the record. |
| **Linked records** | Records in other modules that link to this record. |
| **Files** | Files attached to the record. |
| **History** | Who changed the record, and when. Only people with the right access see this tab. |
| **Sheets** | Sheets on this record, and **Appears in**: rows of other sheets that link to this record. |

To move to the next or previous record, select **Next record** or **Previous record**. To close the panel, select **Close**.

To give a colleague a link to the record, select **More record actions**, then **Copy link**. (unverified: the place of **Copy link** in the record panel.)

### 3.4 Add a record

You need **Write** on the module.

1. On the **Records** tab, select **New record**.
2. Fill in the fields.
3. Select the create button. It shows the module name, for example "Create Orders record".

To add more than one record, select **Create and add another**. The dialog stays open for the next record.

To stop without a new record, select **Cancel**.

### 3.5 Change a record

You need **Write** on the module.

1. Open the record.
2. Select **Edit**.
3. Change the fields.
4. Select **Save changes**.

If someone else changed the record while you edited it, Slate Operations shows "This record changed after you opened it". Select **Load latest values**. Then make your change again.

To change one field on many records at the same time:

1. In the **Table** layout, select the rows.
2. In the bar that shows how many are selected, select **Change**.
3. Choose the field. Only choice-list and checkbox fields are available.
4. Choose the new value and confirm.

To stop, select **Clear selection**.

### 3.6 Delete and restore a record

You need **Write** on the module.

1. Open the record.
2. Select **More record actions**.
3. Select **Delete record**.

Slate Operations shows "Record deleted." with **Undo**. Select **Undo** to bring the record back at once.

To restore a record later:

1. Select **Filters**.
2. In **Deleted**, choose **Show only deleted records**.
3. Open the record.
4. Select **Restore record**.

Only an administrator can delete a record forever.

### 3.7 Export records

1. On the **Records** tab, set the search and filters that you need.
2. Select **Export**.
3. In **Export records**, choose **CSV** or **Excel (.xlsx)** in **Format**.
4. Select the columns that you want.
5. Select **Download records**.

An export can hold up to 10,000 rows. If your list is larger, add a filter and export again.

### 3.8 Department dashboards

1. Under **Departments**, select your department.
2. Select **Dashboard**.

The dashboard shows widgets: charts and numbers from the records of the department. A widget does not give you access to its records. To get the latest numbers, select **Refresh**.

People with **Manage** on the department can change the dashboard with **Edit layout**, **Add widget**, and **Save layout**.

### 3.9 Reports

A report is a saved list of records that Slate Operations can copy now or on a schedule. Each copy keeps the rows as they were at that time.

To read a report:

1. Open the module page.
2. Select the **Reports** tab.
3. Select a report.
4. Select **Open copy** on the copy that you want.
5. Select **Print** to print it, or **CSV** to download it.

To make a new copy now, select **Make a copy now**.

People with **Manage** on the module make reports. They use **New report**, **Make a report from the current view**, or **Start from scratch**.

### 3.10 Sheets

A sheet is your own table on a record or a module. Use it for notes, checklists, costs, or plans next to your records. A sheet never changes the record.

Only you can see a new sheet until you share it. Guests cannot create sheets.

You find sheets in three places:

- The **Sheets** tab of a record.
- The **Sheets** tab of a module page.
- **My sheets** in the foot of the sidebar.

#### Make a sheet

1. Open a record, or a module page.
2. Select the **Sheets** tab.
3. Select **New sheet**.
4. Type a name in **Name**.
5. In **Start with**, choose **Blank sheet**, **Template file**, or **Data file**.
6. Select **Create sheet**.

**Template file** uses a .json file with the columns of another sheet. **Data file** uses a CSV or Excel file with rows. For a data file, select **Check the rows** in step 6. You check the rows before Slate Operations adds them.

#### Add columns and rows

1. Open the sheet.
2. Select **Add column**.
3. Type a name in **Name**.
4. Choose a type in **Type**.
5. Select **Add column**.
6. Select **Add row** to add a row.
7. Type values in the cells.

The column types are:

| Type | What it holds |
|---|---|
| **Text**, **Long text** | Words. |
| **Number**, **Whole number** | Numbers. |
| **Checkbox** | Yes or no. |
| **Date**, **Date and time** | A date, or a date with a time. |
| **Choice list** | One value from a list. |
| **User** | A person in your organization. |
| **Email**, **Web link** | An email address, or a web address. |
| **Link to records** | A link to one record of a module that you can read. |
| **Lookup** | A field of the linked record. You cannot type in it. |
| **From another sheet** | A column of another sheet, from the row that links the same record. You cannot type in it. |
| **Computed** | A value that Slate Operations calculates from numbers in the same row. You cannot type in it. |

To delete a row, select **Delete row** on that row. To change or delete a column, open its settings. Then select **Save column** or **Delete column**.

To find a value, type in **Search this sheet**.

#### Share a sheet

Only the owner of a sheet can share it.

1. Open the sheet.
2. Select **Share**.
3. In **Add people or groups**, choose a person or a group.
4. In **Level**, choose **View** or **Edit**.
5. Select **Share**.
6. Select **Done**.

**View** lets a person read and export the sheet. **Edit** also lets them change rows and columns. A guest can get **View** only. A share does not give access to the record.

When the owner of a sheet leaves the organization, the sheet becomes open. Everyone who can read its record can read the sheet. Nobody can change or delete it.

#### Other sheet actions

The sheet header has these actions:

| Action | What it does |
|---|---|
| **Import** | Adds rows from a file. |
| **Export** | Downloads the sheet: **Download CSV**, **Download Excel**, or **Download template** (columns only). |
| **Make a copy** | Makes your own copy of the sheet. |
| **More sheet actions** | Opens **Rename**, **Sheet history**, **New sheet from this structure**, and **Delete sheet**. |

#### Find your sheets

1. Select **My sheets** in the foot of the sidebar.
2. Choose **All**, **Owned by me**, **Shared with me**, or **Deleted**.
3. Type in **Search sheets** to find a sheet by name.

To bring back a sheet that you deleted, choose **Deleted**. Then select **Restore** on that sheet.

## 4. Boards

[Source: `frontend/src/components/boards-navigation-model.ts`, `frontend/src/components/systems/boards/components/` (mainly `board-page-header.tsx`, `server-backed-board-posts.tsx`, `board-post-list.tsx`, `server-backed-board-post-editor.tsx`, `server-backed-board-calendar.tsx`, `server-backed-board-event-editor.tsx`, `board-kanban-board.tsx`, `board-kanban-composer.tsx`, `board-kanban-card.tsx`, `board-card-sheet.tsx`, `server-backed-board-gantt.tsx`), `frontend/src/components/systems/boards/domain/post-list.ts`]

A board is a shared page for a team. It holds posts, events, and cards.

There are three kinds of board:

- The **Company** board is for the whole organization. Everyone reads it. Only administrators change it.
- Each department has its own board. Open it with **Announcements** under the department.
- A project board is for one project. Administrators make project boards and choose who has access.

### 4.1 Open a board

1. In the sidebar, open **Boards** under **Tools**.
2. Select **Company**, a project board, or **All boards**.

To open a department board, select **Announcements** under your department.

Each board has four tabs:

| Tab | What it holds |
|---|---|
| **Posts** | Updates and news. |
| **Calendar** | Events with dates. |
| **Kanban** | Cards that move through stages. |
| **Gantt** | The cards on a time line. |

What you can do on a board depends on your access level on that board.

### 4.2 Read posts

1. Open the board.
2. Select **Posts**.
3. Select a post to read it.
4. Select **Back to posts** to go back to the list.

To find a post, type in **Search posts**. To filter by author, select **Filters**. A pinned post stays at the top and shows **Pinned**.

If you can only read the board, you see the published posts. With **Write**, you also see **Scheduled** and **Drafts**. With **Manage**, you also see **Archived**.

### 4.3 Write a post

You need **Write** on the board.

1. Open the board and select **Posts**.
2. Select **New post**.
3. Type a title in **Title**.
4. Type the text in **Message**.
5. To attach a file, select **Choose file**.
6. To add a web link, select **Add link**.
7. Select **Publish post**.

To keep the post as a draft, select **Save draft**. Only people who can write on the board see drafts.

To publish later:

1. Select **Schedule…**.
2. Set the date and time in **Publish at**.
3. Select **Schedule**.

To change a post, open it and select **Edit**. A changed post shows **Edited**. Readers can open its earlier revisions.

### 4.4 Use the calendar

1. Open the board and select **Calendar**.
2. Choose **Month** or **Week**.
3. Select an event to read it.

To add an event:

1. Select **New event**.
2. Type a name in **Event title**.
3. Set the date and time in **When**. Select **All day** for an event with no time.
4. To repeat the event, choose an option in **Repeats**.
5. Type the place in **Location** and more text in **Details**.
6. In **Reminders**, choose **When it starts**, **15 minutes before**, or **1 day before**.
7. Select **Create event**.

You add files and linked records after you create the event.

To change an event, open it and select **Edit**. Then select **Save event**.

### 4.5 My calendar

My calendar shows the events of all the boards that you can read in one calendar.

1. In **Boards**, select **My calendar**.
2. In **Calendars**, tick a calendar to show it. Clear the tick to hide it.

To add a board calendar to My calendar, open the board calendar and select **Add to My calendar**. (unverified: the exact place of this button.)

### 4.6 Use the Kanban

The Kanban shows cards in stages, for example "To do", "Doing", and "Done". A card is a task that you name, or a record that you find.

To add a card, you need **Write** on the board.

1. Open the board and select **Kanban**.
2. Under a stage, select **Add a card**.
3. Type the name in **Card title**.
4. Select **Add card**.

To add a record as a card, select **Find a record** in step 3. Then choose the record and select **Add card**.

To move a card:

1. Drag the card to the stage that you want.

You can also open the card menu and select **Move to stage**.

To open a card, select it. The card has the tabs **Details**, **Files**, **Linked records**, and **Activity**.

To find a card, type in **Search cards**. To filter by person, label, or date, select **Filters**.

Board managers add and change stages.

Keyboard: on the Kanban, Space lifts a card. The arrow keys move it. Space drops it. Escape puts it back.

### 4.7 Use the Gantt

The Gantt shows the cards with dates on a time line.

1. Open the board and select **Gantt**.
2. Choose **Week** or **Month**.
3. Drag a bar to change its dates.
4. Select **Save changes**.

To cancel your changes before you save, select **Discard**. A card with no dates shows **Add dates**.

Keyboard: Left and Right move a bar one day. Shift with Left or Right changes the due date.

## 5. OpenComms

[Source: `frontend/src/components/systems/comms/components/` (mainly `conversation-list.tsx`, `conversation-header.tsx`, `conversation-view.tsx`, `message-composer.tsx`, `message-timeline.tsx`, `floating.tsx`, `thread-panel.tsx`, `direct-dialog.tsx`, `comms-menu.tsx`), `frontend/src/components/app-shell.tsx`]

OpenComms is where you send messages to your colleagues. It has channels for teams and topics, and direct messages for one or more people.

Your access decides which conversations you can open. A link in a message does not give you access to the linked record or file.

### 5.1 Open OpenComms

1. Select **OpenComms** in the foot of the sidebar.

The list on the left has these parts:

- **Inbox**, **Activity**, **Threads**, and **Browse channels** at the top.
- **Starred**: conversations that you marked with a star.
- **Channels**: the channels that you belong to.
- **Records you follow**: conversations about records.
- **Direct messages**: your conversations with one or more people.

To find a conversation, type in **Find a conversation…**.

To find a channel that is not in your list, select **Browse channels**.

### 5.2 Send a message

1. Select a channel or a direct message.
2. Type your text in the message box at the bottom.
3. Press Enter, or select **Send message**.

The box tells you which key sends: **Enter to send** or **Ctrl + Enter to send**. You can change this in **My preferences** in the **OpenComms menu**. (unverified: the place of this setting.)

To add more to your message:

- To name a colleague, type @ and the name. Then choose the person in the list. The person gets a notification.
- To attach a file, select **Upload files**.
- To attach a record, select **Attach record**.
- To send the message later, select **Schedule send**. Then set **Send at (local time)**.

### 5.3 When a message does not send

Slate Operations sends a message only after the server accepts it. While it sends, you see **Sending…**.

If the message did not send, you see **Not sent**.

1. Select **Retry message**.

Your text stays in the box until the server accepts it.

### 5.4 Reply, react, and use threads

Each message has a menu. To open it, select the **Message actions** button on the message, or right-click the message.

| Menu item | What it does |
|---|---|
| **Add reaction** | Adds an emoji to the message. |
| **Reply** | Starts a reply to this message in the conversation. |
| **Create thread** | Opens a thread: a side conversation about this message. |
| **Pin message** | Keeps the message in the pinned list of the conversation. |
| **Edit message** | Changes your own message. Select **Save message** when you finish. |
| **Edit history** | Shows earlier versions of the message. |
| **Report message** | Sends a message by someone else to the moderators. |
| **Delete message** | Removes your message. |

When you reply, the box shows **Replying to** and the name. To stop, select **Cancel reply**.

In a thread:

1. Type your reply.
2. Select **Send reply**.

To also show the reply in the channel, tick **Also send to channel**. To get notifications for new replies, select **Follow**. To go back, select **Back to messages**.

### 5.5 Start a direct message

1. Under **Direct messages**, select **Start direct message**.
2. Choose **Direct message** for one person, or **Group message** for more people.
3. Choose the person or people.
4. For a group, type a name in **Group name**.
5. Select **Start conversation**.

Guests cannot start conversations.

### 5.6 Find a message

1. Open the conversation.
2. Type a word in **Search messages** at the top.

To search all of Slate Operations, use **Search** in the top bar (see 1.4).

### 5.7 Choose your notifications

Each conversation can notify you about **All** messages, only **Mentions**, or nothing (**Mute**).

1. Open the conversation menu.
2. Choose **All**, **Mentions**, or **Mute** in **Conversation notifications**.

(unverified: the exact place of the conversation menu.)

### 5.8 Keyboard

When **Use shortcuts** is on, press Ctrl+K (Windows) or Command+K (Mac) in OpenComms to switch to another conversation.

## Blanks in this guide

The seller fills in these items before giving the guide to a customer:

- [support contact]: who to contact for help with Slate Operations.
- [Slate Operations address]: the web address that people open to sign in.
