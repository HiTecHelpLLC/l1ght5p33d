// SPDX-License-Identifier: MIT
// Synthetic local UI. No network, files, credentials, or real creative content.
using System;
using System.Drawing;
using System.Windows.Forms;

public sealed class CreatorFixture : Form
{
    private readonly Label status;
    private readonly TextBox titleEditor;

    public CreatorFixture()
    {
        Text = "CreateRelay Creative Fixture";
        Name = "CreatorFixture";
        ClientSize = new Size(600, 300);
        StartPosition = FormStartPosition.CenterScreen;
        AutoScaleMode = AutoScaleMode.Dpi;

        var label = new Label { Text = "Artwork title", Location = new Point(24, 24), AutoSize = true };
        titleEditor = new TextBox { Name = "titleEditor", AccessibleName = "Artwork title", Location = new Point(24, 52), Width = 350 };
        var apply = new Button { Name = "applyTitle", AccessibleName = "Apply title", Text = "Apply title", Location = new Point(390, 50), Size = new Size(130, 32) };
        status = new Label { Name = "statusText", AccessibleName = "Status", Text = "Ready", Location = new Point(24, 112), Size = new Size(530, 35) };
        apply.Click += delegate { status.Text = "Applied: " + titleEditor.Text; };

        // Deliberately drawn custom surface: no accessible child button exists.
        // Its Panel remains discoverable for local calibration, while activation
        // exercises a template fallback after a semantic button lookup misses.
        var canvas = new Panel { Name = "stampCanvas", AccessibleName = "Stamp canvas", Location = new Point(24, 166), Size = new Size(170, 80), BackColor = Color.White };
        canvas.Paint += delegate(object sender, PaintEventArgs e) {
            e.Graphics.Clear(Color.White);
            using (var fill = new SolidBrush(Color.FromArgb(28, 96, 142)))
                e.Graphics.FillRectangle(fill, 6, 6, 158, 68);
            e.Graphics.DrawRectangle(Pens.Orange, 10, 10, 150, 60);
            using (var font = new Font("Segoe UI", 17, FontStyle.Bold))
                e.Graphics.DrawString("STAMP", font, Brushes.White, 30, 23);
            e.Graphics.DrawLine(Pens.Orange, 15, 65, 155, 15);
        };
        canvas.MouseClick += delegate { status.Text = "Stamped"; };
        Controls.AddRange(new Control[] { label, titleEditor, apply, status, canvas });
        Shown += delegate { Activate(); titleEditor.Focus(); };
    }

    [STAThread]
    public static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new CreatorFixture());
    }
}
