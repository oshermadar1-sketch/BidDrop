import { useState } from "react";
import { View, Text, Button, TextInput, Alert } from "react-native";
import {
  createShipment,
  placeBid,
  closeAuction,
  declareWinner,
  getShipment,
} from "../src/api/pobaClient";
import React from "react";

export default function PobaDemoScreen() {
  const [shipmentId, setShipmentId] = useState<number | null>(null);
  const [price, setPrice] = useState("100");
  const [detailsURI, setDetailsURI] = useState("ipfs://placeholder");

  async function onCreate() {
    try {
      const deadline = Math.floor(Date.now() / 1000) + 24 * 60 * 60; // +1 יום
      const { id } = await createShipment({ detailsURI, deadline });
      setShipmentId(id);
      Alert.alert("Created", `Shipment #${id}`);
    } catch (e: any) {
      Alert.alert("Error", e.message);
    }
  }

  async function onBid() {
    if (shipmentId == null) return Alert.alert("Create a shipment first");
    try {
      await placeBid(shipmentId, Number(price));
      Alert.alert("Bid placed", `#${shipmentId} price=${price}`);
    } catch (e: any) {
      Alert.alert("Error", e.message);
    }
  }

  async function onClose() {
    if (shipmentId == null) return;
    try {
      await closeAuction(shipmentId);
      Alert.alert("Auction closed");
    } catch (e: any) {
      Alert.alert("Error", e.message);
    }
  }

  async function onDeclare() {
    if (shipmentId == null) return;
    try {
      const res = await declareWinner(shipmentId);
      Alert.alert("Winner", `${res.winner} @ ${res.price}`);
    } catch (e: any) {
      Alert.alert("Error", e.message);
    }
  }

  async function onRefresh() {
    if (shipmentId == null) return;
    try {
      const { shipment, bids } = await getShipment(shipmentId);
      Alert.alert("State", JSON.stringify({ shipment, bids }, null, 2));
    } catch (e: any) {
      Alert.alert("Error", e.message);
    }
  }

  return (
    <View style={{ padding: 16, gap: 12 }}>
      <Text style={{ fontSize: 20, fontWeight: "600" }}>PoBA Demo</Text>

      <TextInput
        value={detailsURI}
        onChangeText={setDetailsURI}
        placeholder="detailsURI"
        style={{ borderWidth: 1, padding: 8, borderRadius: 8 }}
      />

      <Button title="Create Shipment" onPress={onCreate} />

      <View style={{ height: 12 }} />

      <Text>Shipment ID: {shipmentId ?? "-"}</Text>

      <TextInput
        value={price}
        onChangeText={setPrice}
        keyboardType="numeric"
        placeholder="bid price"
        style={{ borderWidth: 1, padding: 8, borderRadius: 8 }}
      />
      <Button title="Place Bid" onPress={onBid} />

      <View style={{ height: 12 }} />
      <Button title="Close Auction" onPress={onClose} />
      <View style={{ height: 12 }} />
      <Button title="Declare Winner" onPress={onDeclare} />
      <View style={{ height: 12 }} />
      <Button title="Refresh State" onPress={onRefresh} />
    </View>
  );
}
