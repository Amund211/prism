import { Close, CloudUpload } from "@mui/icons-material";
import {
    Alert,
    Box,
    Button,
    Checkbox,
    FormControlLabel,
    IconButton,
    LinearProgress,
    List,
    ListItem,
    Stack,
    TextField,
    Tooltip,
    Typography,
} from "@mui/material";
import { createFileRoute, Link } from "@tanstack/react-router";
import React from "react";

import { checkScreenshot, MAX_FILES, MAX_TOTAL_BYTES } from "#helpers/upload.ts";
import type { ScreenshotCheck } from "#helpers/upload.ts";
import { submitUpload, UploadRejectedError } from "#queries/uploads.ts";

const LAUNCHERS = [
    ["official", "Official Minecraft Launcher"],
    ["lunar", "Lunar Client"],
    ["badlion", "Badlion Client"],
    ["feather", "Feather Client"],
    ["labymod", "LabyMod"],
    ["prism-launcher", "Prism Launcher"],
    ["multimc", "MultiMC"],
    ["curseforge", "CurseForge"],
    ["modrinth", "Modrinth App"],
    ["other", "Other"],
] as const;

// 1.8.9 first: most Bed Wars players use it.
const VERSIONS = ["1.8.9", "1.12.2", "1.20.x", "1.21.x", "26.1.x", "other"] as const;

const GUI_SCALES = ["auto", "1", "2", "3", "4", "5", "6"] as const;

const VERSION_PATTERN = /^\d+(?:\.\d+){1,2}$/;

interface SelectedFile {
    readonly id: string;
    readonly file: File;
    readonly previewUrl: string;
    readonly check: ScreenshotCheck | null;
    readonly sent: boolean;
}

interface Fields {
    readonly launcher: string;
    readonly launcherOther: string;
    readonly mcVersion: string;
    readonly mcVersionOther: string;
    readonly resourcePack: string;
    readonly guiScale: string;
    readonly contact: string;
    readonly note: string;
}

const EMPTY_FIELDS: Fields = {
    launcher: "",
    launcherOther: "",
    mcVersion: "",
    mcVersionOther: "",
    resourcePack: "",
    guiScale: "",
    contact: "",
    note: "",
};

const fieldsBlockedReason = (fields: Fields): string | null => {
    if (fields.launcher === "") {
        return "Choose your launcher.";
    }
    if (fields.launcher === "other" && fields.launcherOther.trim() === "") {
        return "Write the name of your launcher.";
    }
    if (fields.mcVersion === "") {
        return "Choose your Minecraft version.";
    }
    if (
        fields.mcVersion === "other" &&
        !VERSION_PATTERN.test(fields.mcVersionOther.trim())
    ) {
        return "Write your Minecraft version as a number, for example 1.17.1.";
    }
    return null;
};

// Only the fields flashlight expects: the "other" text only with "other",
// and no empty optional fields.
const fieldsForUpload = (fields: Fields): Record<string, string> => {
    const out: Record<string, string> = {
        launcher: fields.launcher,
        mcVersion: fields.mcVersion,
    };
    if (fields.resourcePack.trim() !== "") {
        out.resourcePack = fields.resourcePack.trim();
    }
    if (fields.guiScale !== "") {
        out.guiScale = fields.guiScale;
    }
    if (fields.launcher === "other") {
        out.launcherOther = fields.launcherOther.trim();
    }
    if (fields.mcVersion === "other") {
        out.mcVersionOther = fields.mcVersionOther.trim();
    }
    if (fields.contact.trim() !== "") {
        out.contact = fields.contact.trim();
    }
    if (fields.note.trim() !== "") {
        out.note = fields.note.trim();
    }
    return out;
};

const Instructions = () => (
    <Stack sx={{ gap: 1 }}>
        <Typography variant="body1">
            Help us teach Prism to read the tab list. Send us a few screenshots of the
            tab list from Bed Wars games. It takes about two minutes.
        </Typography>
        <Box component="ol" sx={{ m: 0, pl: 3 }}>
            <li>
                In a Bed Wars game, hold <strong>Tab</strong> and press{" "}
                <strong>F2</strong> (on some laptops: Fn + F2). Do this 2–3 times during
                the game. Chat says &quot;Saved screenshot as …&quot;.
            </li>
            <li>
                To find the files: press Esc → Options → Resource Packs → Open Resource
                Pack Folder. Go one folder back and open the <code>screenshots</code>{" "}
                folder. Lunar and Badlion may use their own folder.
            </li>
            <li>
                Add the screenshots below. Send the original files: do not crop, edit or
                convert them.
            </li>
        </Box>
    </Stack>
);

const SelectField = ({
    label,
    value,
    onChange,
    options,
    optional = false,
}: {
    readonly label: string;
    readonly value: string;
    readonly onChange: (value: string) => void;
    readonly options: readonly (readonly [string, string])[];
    readonly optional?: boolean;
}) => (
    <TextField
        select
        label={label}
        value={value}
        onChange={(event) => {
            onChange(event.target.value);
        }}
        slotProps={{ select: { native: true }, inputLabel: { shrink: true } }}
    >
        <option value="" disabled={!optional}>
            {optional ? "Not set" : "Choose…"}
        </option>
        {options.map(([optionValue, optionLabel]) => (
            <option key={optionValue} value={optionValue}>
                {optionLabel}
            </option>
        ))}
    </TextField>
);

const FilePicker = ({
    onAdd,
    disabled,
}: {
    readonly onAdd: (files: readonly File[]) => void;
    readonly disabled: boolean;
}) => {
    const [dragging, setDragging] = React.useState(false);
    return (
        <Box
            onDragOver={(event) => {
                event.preventDefault();
                setDragging(!disabled);
            }}
            onDragLeave={() => {
                setDragging(false);
            }}
            onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                if (!disabled) {
                    onAdd([...event.dataTransfer.files]);
                }
            }}
            sx={{
                border: 2,
                borderStyle: "dashed",
                borderColor: dragging ? "primary.main" : "divider",
                borderRadius: 2,
                p: 3,
                textAlign: "center",
                opacity: disabled ? 0.5 : 1,
            }}
        >
            <Stack sx={{ gap: 1, alignItems: "center" }}>
                <Typography variant="body1">
                    Drag screenshots here, or choose them. You can select many at once.
                </Typography>
                <Button
                    component="label"
                    variant="outlined"
                    startIcon={<CloudUpload />}
                    disabled={disabled}
                >
                    Choose files
                    <input
                        hidden
                        disabled={disabled}
                        type="file"
                        accept="image/png"
                        multiple
                        aria-label="Choose screenshots"
                        onChange={(event) => {
                            onAdd([...(event.target.files ?? [])]);
                            // Allow choosing the same file again after removing it.
                            event.target.value = "";
                        }}
                    />
                </Button>
            </Stack>
        </Box>
    );
};

const checkMessage = (check: ScreenshotCheck | null): string | null => {
    if (check === null) {
        return "Checking…";
    }
    return check.ok ? check.warning : check.reason;
};

const FileRow = ({
    item,
    onRemove,
    disabled,
}: {
    readonly item: SelectedFile;
    readonly onRemove: () => void;
    readonly disabled: boolean;
}) => {
    const message = checkMessage(item.check);
    const isError = item.check?.ok === false;
    return (
        <ListItem
            disableGutters
            secondaryAction={
                <IconButton
                    aria-label={`Remove ${item.file.name}`}
                    onClick={onRemove}
                    disabled={disabled}
                >
                    <Close />
                </IconButton>
            }
        >
            <Stack direction="row" sx={{ gap: 2, alignItems: "center", minWidth: 0 }}>
                <Box
                    component="img"
                    src={item.previewUrl}
                    alt=""
                    sx={{ width: 96, height: 54, objectFit: "cover", borderRadius: 1 }}
                />
                <Stack sx={{ minWidth: 0 }}>
                    <Typography variant="body2" noWrap>
                        {item.file.name}
                        {item.sent && " ✓"}
                    </Typography>
                    {message !== null && (
                        <Typography
                            variant="caption"
                            color={isError ? "error" : "warning.main"}
                        >
                            {message}
                        </Typography>
                    )}
                </Stack>
            </Stack>
        </ListItem>
    );
};

function RouteComponent() {
    const [files, setFiles] = React.useState<readonly SelectedFile[]>([]);
    const [fields, setFields] = React.useState<Fields>(EMPTY_FIELDS);
    const [consent, setConsent] = React.useState(false);
    const [uploading, setUploading] = React.useState(false);
    const [uploadId, setUploadId] = React.useState<string | null>(null);
    const [uploadError, setUploadError] = React.useState<string | null>(null);
    const [tooMany, setTooMany] = React.useState(false);

    // Free the previews when the page goes away.
    const filesRef = React.useRef(files);
    React.useEffect(() => {
        filesRef.current = files;
    }, [files]);
    React.useEffect(
        () => () => {
            for (const item of filesRef.current) {
                URL.revokeObjectURL(item.previewUrl);
            }
        },
        [],
    );

    const updateFile = (id: string, update: Partial<SelectedFile>) => {
        setFiles((current) =>
            current.map((item) => (item.id === id ? { ...item, ...update } : item)),
        );
    };

    // The selection is fixed while it uploads and after it is sent.
    const locked = uploading || uploadId !== null;

    const addFiles = (added: readonly File[]) => {
        if (locked) {
            return;
        }
        const room = MAX_FILES - files.length;
        setTooMany(added.length > room);
        const items = added.slice(0, Math.max(room, 0)).map((file): SelectedFile => ({
            id: crypto.randomUUID(),
            file,
            previewUrl: URL.createObjectURL(file),
            check: null,
            sent: false,
        }));
        setFiles((current) => [...current, ...items]);
        for (const item of items) {
            void (async () => {
                updateFile(item.id, { check: await checkScreenshot(item.file) });
            })();
        }
    };

    const removeFile = (id: string) => {
        setTooMany(false);
        setFiles((current) => {
            const item = current.find((candidate) => candidate.id === id);
            if (item !== undefined) {
                URL.revokeObjectURL(item.previewUrl);
            }
            return current.filter((candidate) => candidate.id !== id);
        });
    };

    const setField = (name: keyof Fields) => (value: string) => {
        setFields((current) => ({ ...current, [name]: value }));
    };

    const allChecked = files.every((item) => item.check?.ok === true);
    const totalBytes = files.reduce((sum, item) => sum + item.file.size, 0);
    const tooLarge = totalBytes > MAX_TOTAL_BYTES;
    const blockedReason = ((): string | null => {
        if (uploading) {
            return "The upload is running.";
        }
        if (files.length === 0) {
            return "Add at least one screenshot.";
        }
        if (files.some((item) => item.check === null)) {
            return "The screenshots are being checked.";
        }
        if (!allChecked) {
            return "Remove the files marked in red.";
        }
        if (tooLarge) {
            return "The screenshots are too large in total. Remove some.";
        }
        return fieldsBlockedReason(fields) ?? (consent ? null : "Agree to the terms.");
    })();
    const sentCount = files.filter((item) => item.sent).length;

    const upload = async () => {
        setUploading(true);
        setUploadError(null);
        // A failed upload is discarded by the server, so every try sends all files.
        setFiles((current) => current.map((item) => ({ ...item, sent: false })));
        const selected = files;
        try {
            const id = await submitUpload({
                kind: "tabcap",
                fields: fieldsForUpload(fields),
                files: selected.map((item) => item.file),
                onFileDone: (index) => {
                    updateFile(selected[index].id, { sent: true });
                },
            });
            setUploadId(id);
        } catch (error: unknown) {
            setUploadError(
                error instanceof UploadRejectedError
                    ? error.message
                    : "Upload failed. Check your connection and try again.",
            );
        }
        setUploading(false);
    };

    const startOver = () => {
        for (const item of files) {
            URL.revokeObjectURL(item.previewUrl);
        }
        setFiles([]);
        setUploadId(null);
        setUploadError(null);
    };

    return (
        <Stack sx={{ gap: 3, maxWidth: 720 }}>
            <meta
                name="description"
                content="Send tab-list screenshots from Hypixel Bed Wars to help develop the Prism Overlay."
            />
            <link rel="canonical" href="https://prismoverlay.com/contribute/tabcap" />
            <Typography variant="h4" component="h1">
                Send tab-list screenshots
            </Typography>
            <Instructions />

            <Stack sx={{ gap: 1 }}>
                <FilePicker onAdd={addFiles} disabled={locked} />
                {tooMany && (
                    <Alert severity="warning">
                        You can add up to {MAX_FILES} screenshots at a time.
                    </Alert>
                )}
                {tooLarge && (
                    <Alert severity="warning">
                        The screenshots are larger than{" "}
                        {(MAX_TOTAL_BYTES / 1024 / 1024).toString()} MB in total. Remove
                        some, and send them in a second upload.
                    </Alert>
                )}
                {files.length > 0 && (
                    <List dense>
                        {files.map((item) => (
                            <FileRow
                                key={item.id}
                                item={item}
                                disabled={locked}
                                onRemove={() => {
                                    removeFile(item.id);
                                }}
                            />
                        ))}
                    </List>
                )}
            </Stack>

            <Stack sx={{ gap: 2 }}>
                <Typography variant="h6" component="h2">
                    About your game
                </Typography>
                <Typography variant="body2" color="text.secondary">
                    All fields are required, except the ones marked optional.
                </Typography>
                <SelectField
                    label="Launcher"
                    value={fields.launcher}
                    onChange={setField("launcher")}
                    options={LAUNCHERS}
                />
                {fields.launcher === "other" && (
                    <TextField
                        label="Name of your launcher"
                        value={fields.launcherOther}
                        onChange={(event) => {
                            setField("launcherOther")(event.target.value);
                        }}
                        slotProps={{ htmlInput: { maxLength: 100 } }}
                    />
                )}
                <SelectField
                    label="Minecraft version"
                    value={fields.mcVersion}
                    onChange={setField("mcVersion")}
                    options={VERSIONS.map((version) => [
                        version,
                        version === "other" ? "Other" : version,
                    ])}
                />
                {fields.mcVersion === "other" && (
                    <TextField
                        label="Version number"
                        placeholder="1.17.1"
                        value={fields.mcVersionOther}
                        onChange={(event) => {
                            setField("mcVersionOther")(event.target.value);
                        }}
                        slotProps={{ htmlInput: { maxLength: 20 } }}
                    />
                )}
                <TextField
                    label="Resource pack (optional)"
                    helperText="The pack that changes your font, if any."
                    value={fields.resourcePack}
                    onChange={(event) => {
                        setField("resourcePack")(event.target.value);
                    }}
                    slotProps={{ htmlInput: { maxLength: 200 } }}
                />
                <SelectField
                    label="GUI scale (optional)"
                    value={fields.guiScale}
                    onChange={setField("guiScale")}
                    optional
                    options={GUI_SCALES.map((scale) => [
                        scale,
                        scale === "auto" ? "Auto" : scale,
                    ])}
                />
                <TextField
                    label="Discord name (optional)"
                    helperText="So we can ask you about your screenshots."
                    value={fields.contact}
                    onChange={(event) => {
                        setField("contact")(event.target.value);
                    }}
                    slotProps={{ htmlInput: { maxLength: 100 } }}
                />
                <TextField
                    label="Note (optional)"
                    multiline
                    minRows={2}
                    value={fields.note}
                    onChange={(event) => {
                        setField("note")(event.target.value);
                    }}
                    slotProps={{ htmlInput: { maxLength: 1000 } }}
                />
                <FormControlLabel
                    control={
                        <Checkbox
                            checked={consent}
                            onChange={(event) => {
                                setConsent(event.target.checked);
                            }}
                        />
                    }
                    label={
                        <>
                            I agree that Prism Overlay stores these screenshots and the
                            details above, and uses them to develop and test the
                            overlay. The screenshots can show other players&apos; names
                            and chat. See the <Link to="/privacy">privacy policy</Link>.
                        </>
                    }
                />
            </Stack>

            <Stack sx={{ gap: 1 }}>
                {uploading && (
                    <LinearProgress
                        variant="determinate"
                        value={(sentCount / files.length) * 100}
                        aria-label="Upload progress"
                    />
                )}
                {uploadError !== null && <Alert severity="error">{uploadError}</Alert>}
                {uploadId === null ? (
                    <Tooltip title={blockedReason ?? ""}>
                        {/* A disabled button gets no hover events. */}
                        <Box component="span" sx={{ display: "flex" }}>
                            <Button
                                variant="contained"
                                disabled={blockedReason !== null}
                                fullWidth
                                onClick={() => {
                                    void upload();
                                }}
                            >
                                {uploadError === null ? "Upload" : "Try again"}
                            </Button>
                        </Box>
                    </Tooltip>
                ) : (
                    <Alert
                        severity="success"
                        action={<Button onClick={startOver}>Send more</Button>}
                    >
                        <Typography variant="body1">Thank you!</Typography>
                        <Typography variant="body2">
                            Upload ID: {uploadId}. Give this ID if you want us to delete
                            your screenshots.
                        </Typography>
                    </Alert>
                )}
                {!allChecked &&
                    files.length > 0 &&
                    files.every((f) => f.check !== null) && (
                        <Typography variant="body2" color="error">
                            Remove the files marked in red before you upload.
                        </Typography>
                    )}
            </Stack>
        </Stack>
    );
}

export const Route = createFileRoute("/contribute/tabcap")({
    component: RouteComponent,
});
