// components/AddressAutocomplete.tsx
// Address input with suggestions while typing (Photon by Komoot, OpenStreetMap data, free, no key).
// Picking a suggestion gives exact coordinates, so the server does not need to geocode.
// Free text still works: without a picked suggestion the server geocodes the text as before.
import React, { useEffect, useRef, useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  StyleSheet,
  type StyleProp,
  type TextStyle,
} from "react-native";

const PHOTON_URL = "https://photon.komoot.io/api/";
const ISRAEL_BBOX = "34.2,29.45,35.95,33.35"; // lon_min,lat_min,lon_max,lat_max
const DEBOUNCE_MS = 350;
const MIN_CHARS = 2;

export type PickedAddress = { label: string; lat: number; lon: number };

type PhotonFeature = {
  geometry: { coordinates: [number, number] };
  properties: {
    name?: string;
    street?: string;
    housenumber?: string;
    city?: string;
    town?: string;
    village?: string;
    district?: string;
  };
};

function labelOf(p: PhotonFeature["properties"]): string {
  const place = p.city || p.town || p.village || p.district || "";
  const street = p.street
    ? [p.street, p.housenumber].filter(Boolean).join(" ")
    : "";
  const main = p.name && p.name !== p.street ? p.name : street;
  return [main, main === street ? "" : street, place]
    .filter(Boolean)
    .join(", ");
}

export function AddressAutocomplete({
  value,
  onChangeText,
  onPick,
  placeholder,
  inputStyle,
}: {
  value: string;
  /** Called on every keystroke; the previous pick is no longer valid. */
  onChangeText: (text: string) => void;
  onPick: (picked: PickedAddress) => void;
  placeholder?: string;
  inputStyle?: StyleProp<TextStyle>;
}) {
  const [results, setResults] = useState<PickedAddress[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const lastPicked = useRef<string | null>(null);

  useEffect(() => {
    const q = value.trim();
    if (!open || q.length < MIN_CHARS || q === lastPicked.current) {
      setResults([]);
      return;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(async () => {
      try {
        setLoading(true);
        const url = `${PHOTON_URL}?q=${encodeURIComponent(
          q
        )}&limit=6&bbox=${ISRAEL_BBOX}`;
        const res = await fetch(url, { signal: ctrl.signal });
        const data = await res.json();
        const seen = new Set<string>();
        const items: PickedAddress[] = [];
        for (const f of (data?.features ?? []) as PhotonFeature[]) {
          const label = labelOf(f.properties);
          if (!label || seen.has(label)) continue;
          seen.add(label);
          const [lon, lat] = f.geometry.coordinates;
          items.push({ label, lat, lon });
        }
        setResults(items);
      } catch {
        if (!ctrl.signal.aborted) setResults([]); // offline: free text still works
      } finally {
        if (!ctrl.signal.aborted) setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [value, open]);

  return (
    <View>
      <View>
        <TextInput
          style={inputStyle}
          placeholder={placeholder}
          value={value}
          onChangeText={(t) => {
            lastPicked.current = null;
            setOpen(true);
            onChangeText(t);
          }}
          onFocus={() => setOpen(true)}
          textAlign="right"
          autoCorrect={false}
        />
        {loading && <ActivityIndicator style={S.spinner} size="small" />}
      </View>

      {open && results.length > 0 && (
        <View style={S.list}>
          {results.map((r) => (
            <TouchableOpacity
              key={`${r.label}-${r.lat}-${r.lon}`}
              style={S.item}
              onPress={() => {
                lastPicked.current = r.label;
                setOpen(false);
                setResults([]);
                onChangeText(r.label);
                onPick(r);
              }}
            >
              <Text style={S.itemText} numberOfLines={1}>
                📍 {r.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}

const S = StyleSheet.create({
  spinner: { position: "absolute", left: 12, top: 0, bottom: 0 },
  list: {
    marginTop: 4,
    backgroundColor: "#fff",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#e5e7eb",
    overflow: "hidden",
  },
  item: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#f3f4f6",
  },
  itemText: { textAlign: "right", color: "#111827", fontSize: 14 },
});
