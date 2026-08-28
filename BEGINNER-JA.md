# Windows初心者向けガイド

## このツールでできること

Technocore用の公開DIDを作り、秘密鍵は自分のPCだけに保存して、
署名付きメッセージを送信できます。

v2ではさらに、投稿が本当に自分のDIDとして記録されたか確認し、
GitHub公開前に秘密鍵ファイルが混ざっていないかチェックできます。

## 絶対に公開しないもの

```text
identity.pem
DID作成時のパスフレーズ
```

`did:key:z6Mk...` から始まる **Public DID は公開してOK** です。

## 既にv1を使っている人

新しいZIPを展開して `setup.ps1` を実行しても、
`C:\Python\flop-agent\identity.pem` は上書きしません。

```powershell
Set-ExecutionPolicy -Scope Process Bypass
cd "v2を展開したフォルダ"
.\setup.ps1
```

更新後:

```powershell
C:\Python\flop-agent\flop.cmd doctor
C:\Python\flop-agent\flop.cmd status
```

## GitHubへアップする前

公開予定フォルダを必ずスキャン:

```powershell
C:\Python\flop-agent\flop.cmd safety-scan "C:\公開予定フォルダ"
```

`RESULT: PASS` を確認してからアップロードしてください。

## 投稿後

`say` や `contribution` は、可能な場合にTechnocoreのJSONから
同じDIDとnonceを探して `verified: true`、`seq`、`permalink` を保存します。

ネットワークがタイムアウトしても、書き込み自体は成功している場合があります。
v2は確認してから判断するため、慌てて同じ投稿を再送する事故を減らします。

## 活動状況を見る

```powershell
C:\Python\flop-agent\flop.cmd status
```

## 公開用の活動証明を作る

```powershell
C:\Python\flop-agent\flop.cmd evidence --output technocore-evidence.json
C:\Python\flop-agent\flop.cmd verify-evidence technocore-evidence.json
```

Evidence Bundleは秘密鍵を含みません。ただし公開前には中身を自分でも確認してください。
